import unittest
from portfolio import NaivePortfolio
from data import HistoricCSVDataHandler
from event import SignalEvent, FillEvent
import queue
from datetime import datetime

# todo: need to test the portfolio with multiple tokens
# todo: performance metrics

class TestPortfolio(unittest.TestCase):

    def setUp(self):

        events_queue = queue.Queue()

        self.dataHandler = HistoricCSVDataHandler(
            events=events_queue,
            csv_dir="datasets",
            token_list=["aave_usdc"]
        )

        self.portfolio = NaivePortfolio(
            rates=self.dataHandler,
            events=events_queue,
            start_date='2021-03-11 14:49',
            initial_capital=1000.00
        )

    def test_update_timeindex(self):

        # (Token, Direction = LONG, SHORT or EXIT, Timestamp)
        signal = SignalEvent('aave_usdc', 'LONG', '2021-03-11 14:49')
        self.dataHandler.update_rates()

        self.portfolio.update_timeindex(
            event=signal
        )

        all_holdings = self.portfolio.all_holdings

        # todo: fix since the market value calculation is not done yet
        self.assertEqual(all_holdings[1]['aave_usdc'], 10000)
        self.assertEqual(str(all_holdings[1]['datetime']), '2021-03-11 14:49:24+00:00')
        self.assertEqual(all_holdings[1]['cash'], 1000)
        self.assertEqual(all_holdings[1]['fee'], 0.0)
        self.assertEqual(all_holdings[1]['total'], 11000.0)


    def test_update_positions_from_fill(self):

        self.dataHandler.update_rates()
        self.dataHandler.update_rates()
        self.dataHandler.update_rates()
        self.dataHandler.update_rates()

        currentTimestamp = self.dataHandler.get_latest_rates('aave_usdc', N=1)[0][1]

        fill = FillEvent(
            token='aave_usdc',
            fee=0,
            timestamp=currentTimestamp,
            notional=1000,
            direction='LONG'
        )

        self.portfolio.update_positions_from_fill(
            fill=fill
        )

        latest_position = self.portfolio.current_positions['aave_usdc'][0]

        self.assertEqual(latest_position['timestamp'], currentTimestamp)
        self.assertEqual(latest_position['direction'], "LONG")
        self.assertEqual(latest_position['notional'], 1000)
        self.assertEqual(latest_position['fixedRate'], 0.13201851823382382)
        self.assertEqual(latest_position['startingRateValue'], 1.0000114583092235e+27)
        self.assertEqual(latest_position['fee'], 0.0)


    def test_update_holdings_from_fill(self):

        currentTimestamp = self.dataHandler.get_latest_rates('aave_usdc', N=1)[0][1]

        fill = FillEvent(
            token='aave_usdc',
            fee=10,
            timestamp=currentTimestamp,
            notional=1000,
            direction='LONG'
        )

        self.portfolio.update_holdings_from_fill(
            fill=fill
        )

        self.assertEqual(self.portfolio.current_holdings['cash'], 990)
        self.assertEqual(self.portfolio.current_holdings['total'], 990)

    def test_update_fill(self):

        self.dataHandler.update_rates()
        self.dataHandler.update_rates()
        self.dataHandler.update_rates()

        currentTimestamp = self.dataHandler.get_latest_rates('aave_usdc', N=1)[0][1]

        fill = FillEvent(
            token='aave_usdc',
            fee=10,
            timestamp=currentTimestamp,
            notional=1000,
            direction='LONG'
        )

        self.portfolio.update_fill(
            event=fill
        )

        self.assertEqual(self.portfolio.current_holdings['cash'], 990)
        self.assertEqual(self.portfolio.current_holdings['total'], 990)

        latest_position = self.portfolio.current_positions['aave_usdc'][0]

        self.assertEqual(latest_position['timestamp'], currentTimestamp)
        self.assertEqual(latest_position['direction'], "LONG")
        self.assertEqual(latest_position['notional'], 1000)
        self.assertEqual(latest_position['fixedRate'], 0.013988590453105632)
        self.assertEqual(latest_position['fee'], 10.0)

    def test_generate_naive_order(self):

        # (Token, Direction = LONG, SHORT or EXIT, Timestamp)
        signal = SignalEvent('aave_usdc', 'LONG', '2021-03-11 14:49')

        order = self.portfolio.generate_naive_order(
            signal=signal
        )

        self.assertEqual(order.token, "aave_usdc")
        self.assertEqual(order.timestamp, '2021-03-11 14:49')
        self.assertEqual(order.notional, 10000)
        self.assertEqual(order.direction, 'LONG')


    def test_update_signal(self):

        # (Token, Direction = LONG, SHORT or EXIT, Timestamp)
        signal = SignalEvent('aave_usdc', 'LONG', '2021-03-11 14:49')

        self.portfolio.update_signal(
            event=signal
        )

        order = self.portfolio.events.get()

        self.assertEqual(order.token, "aave_usdc")
        self.assertEqual(order.timestamp, '2021-03-11 14:49')
        self.assertEqual(order.notional, 10000)
        self.assertEqual(order.direction, 'LONG')


    def test_equity_curve_dataframe(self):

        self.dataHandler.update_rates()
        self.dataHandler.update_rates()
        self.dataHandler.update_rates()

        currentTimestamp = self.dataHandler.get_latest_rates('aave_usdc', N=1)[0][1]

        fill = FillEvent(
            token='aave_usdc',
            fee=10,
            timestamp=currentTimestamp,
            notional=1000,
            direction='LONG'
        )

        self.portfolio.update_fill(
            event=fill
        )

        signal = SignalEvent('aave_usdc', 'LONG', '2021-03-11 14:49')

        self.portfolio.update_timeindex(
            event=signal
        )

        self.portfolio.create_equity_curve_dataframe()

        equity_curve = self.portfolio.equity_curve

        self.assertEqual(equity_curve.iloc[1, :]['cash'], 990)
        self.assertEqual(equity_curve.iloc[1, :]['fee'], 10)
        self.assertEqual(equity_curve.iloc[1, :]['total'], 1990.0)
        # corresponds to the market value
        self.assertEqual(equity_curve.iloc[1, :]['aave_usdc'], 1000.0)  ## todo: sanity check with more realistic values
        self.assertEqual(equity_curve.iloc[1, :]['returns'], 0.99) ## todo: sanity check with more realistic values
        self.assertEqual(equity_curve.iloc[1, :]['equity_curve'], 1.99)  ## todo: sanity check with more realistic values




if __name__ == '__main__':
    unittest.main()