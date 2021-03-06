import os, os.path
import pandas as pd
import numpy as np

from abc import ABCMeta, abstractmethod

from event import MarketEvent


class DataHandler(object):
    """
    DataHandler is an abstract base class providing an interface for
    all subsequent (inherited) data handlers (both live and historic).

    The goal of a (derived) DataHandler object is to output a generated
    set of rates for each token requested.

    This will replicate how a live strategy would function as current
    market data would be sent "down the pipe". Thus a historic and live
    system will be treated identically by the rest of the backtesting suite.
    """

    __metaclass__ = ABCMeta

    @abstractmethod
    def get_latest_rates(self, token, N=1):
        """
        Returns the last N rates from the latest_token list,
        or fewer if less rates are available.
        """
        raise NotImplementedError("Should implement get_latest_rates()")

    @abstractmethod
    def update_rates(self):
        """
        Pushes the latest rate to the latest token structure
        for all tokens in the token list.
        """
        raise NotImplementedError("Should implement update_rates()")



class HistoricCSVDataHandler(DataHandler):
    """
    HistoricCSVDataHandler is designed to read CSV files for
    each requested token from disk and provide an interface
    to obtain the "latest" rate in a manner identical to a live
    trading interface.
    """

    def __init__(self, events, csv_dir, token_list, start_date_time=None, end_date_time=None,
                 interpolation_frequency='H', backtest_frequency='D', is_liquid_staking=False):
        """
        Initialises the historic data handler by requesting
        the location of the CSV files and a list of tokens.

        It will be assumed that all files are of the form
        'protocol_token.csv' (e.g. aave_usdc.csv),where token is a string in the list .

        Parameters:
        events - The Event Queue.
        csv_dir - Absolute directory path to the CSV files.
        token_list - A list of token strings.
        """
        self.events = events
        self.csv_dir = csv_dir
        self.token_list = token_list

        self.token_data = {}
        self.latest_token_data = {}
        self.continue_backtest = True

        self.start_date_time = start_date_time
        self.end_date_time = end_date_time
        self.interpolation_frequency = interpolation_frequency
        self.backtest_frequency = backtest_frequency

        self._open_convert_csv_files(
            is_liquid_staking=is_liquid_staking
        )

    def update_rates(self):
        """
        Pushes the latest rate to the latest_symbol_data structure
        for all tokens in the token list.
        """
        for t in self.token_list:
            try:
                rate = next(self._get_new_rate(t))
            except StopIteration:
                self.continue_backtest = False
            else:
                if rate is not None:
                    self.latest_token_data[t].append(rate)
        self.events.put(MarketEvent())

    def get_latest_rates(self, token, N=1):
        """
        Returns the last N rates from the latest_token list,
        or N-k if less available.
        """
        try:
            rates_list = self.latest_token_data[token]
        except KeyError:
            print("That token is not available in the historical data set.")
        else:
            return rates_list[-N:]

    def _get_new_rate(self, token):
        """
        Returns the latest rate (liquidityIndex) from the data feed as a tuple of
        (token, datetime, liquidityIndex).
        """
        for b in self.token_data[token]:
            yield tuple([token, b[0], b[1]['liquidityIndex']])

    def _interpolate_liquidity_index(self, df):

        # resample to follow consistent frequency
        df = df.resample(self.interpolation_frequency).mean()

        # fill in the gaps by interpolating between adjacent known values of the liquidity index
        df = df.interpolate(method='linear')

        return df

    def _removeFlatRegions(self, df):

        # remove observations that are equal to the previous timestep
        df.loc[:, "isNotFlat"] = np.where(
            df.loc[:, "liquidityIndex"] == df.loc[:, "liquidityIndex"].shift(1),
            False,
            True
        )

        df = df.loc[df.loc[:, "isNotFlat"], ["liquidityIndex"]]
        return df

    def _adjust_liquidity_index_frequency(self, df):

        df = df.resample(self.backtest_frequency).ffill()
        df = df.dropna()

        return df

    def _open_convert_csv_files(self, is_liquid_staking=False):
        """
        Opens the CSV files from the data directory, converting
        them into pandas DataFrames within a token dictionary.
.
        """

        comb_index = None
        for t in self.token_list:
            # Load the CSV file with no header information, indexed on date

            self.token_data[t] = pd.io.parsers.read_csv(
                                      os.path.join(self.csv_dir, '%s.csv' % t),
                                      header=0, index_col=0,
                                      names=['date', 'liquidityIndex'],
                                      parse_dates=['date'],
                                      dtype={
                                          'liquidityIndex': "float64"
                                      }
                                  )

            if is_liquid_staking:
                self.token_data[t] = self._removeFlatRegions(
                    df=self.token_data[t]
                )

            # interpolate the liquidity index
            self.token_data[t] = self._interpolate_liquidity_index(
                df=self.token_data[t]
            )

            # change dataset frequency to the one specified by the data handler
            # todo: add frequency to the data handler init function
            self.token_data[t] = self._adjust_liquidity_index_frequency(
                df=self.token_data[t]
            )

            # apply start and end datetime filters if they exist

            if (self.start_date_time and self.end_date_time):

                start_end_filter = self.token_data[t].index.to_series().between(
                    self.start_date_time,
                    self.end_date_time
                )

                self.token_data[t] = self.token_data[t][start_end_filter]

            # remove timezone from dates
            self.token_data[t].index = self.token_data[t].index.tz_localize(None)

            # Combine the index to pad forward values
            if comb_index is None:
                comb_index = self.token_data[t].index
            else:
                comb_index.union(self.token_data[t].index)

            # Set the latest symbol_data to None
            self.latest_token_data[t] = []

        # Reindex the dataframes
        for s in self.token_list:
            self.token_data[s] = self.token_data[s].reindex(index=comb_index, method='pad').iterrows()