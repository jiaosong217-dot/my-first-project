"""Offline unit checks: signal branches and input integrity, not profitability."""
import unittest
import numpy as np
import pandas as pd
from quant_system.now import DURATIONS, Decision, evaluate, format_decision, validate_frame


class DecisionTests(unittest.TestCase):
    def frames(self, short=False):
        row = dict(close=110., ema50=100., ema200=90., macd_hist=1., rsi=60.,
                   atr=2., prior_high20=109., prior_low20=95., volume=200.,
                   vol_sma20=100., close_time=pd.Timestamp('2026-11-08T07:14:59.999Z'))
        if short:
            row.update(close=90., ema50=100., ema200=110., macd_hist=-1., rsi=40.,
                       prior_high20=105., prior_low20=91.)
        return {tf: pd.DataFrame([row]) for tf in DURATIONS}

    def test_long(self):
        d = evaluate('BTCUSDT', self.frames())
        self.assertEqual(d.state, 'LONG')
        self.assertEqual((d.entry, d.stop, d.target), (110., 107., 116.))

    def test_short(self):
        d = evaluate('ETHUSDT', self.frames(True))
        self.assertEqual(d.state, 'SHORT')
        self.assertEqual((d.entry, d.stop, d.target), (90., 93., 84.))

    def test_misaligned_regime(self):
        f = self.frames()
        f['4h'] = self.frames(True)['4h']
        self.assertEqual(evaluate('BTCUSDT', f).state, 'WAIT')

    def test_no_breakout(self):
        f = self.frames()
        f['15m'].loc[0, 'prior_high20'] = 110.
        self.assertEqual(evaluate('BTCUSDT', f).state, 'WAIT')

    def test_weak_volume(self):
        f = self.frames()
        f['15m'].loc[0, 'volume'] = 110.
        self.assertEqual(evaluate('BTCUSDT', f).state, 'WAIT')

    def test_hourly_filter(self):
        f = self.frames()
        f['1h'].loc[0, 'rsi'] = 80.
        self.assertEqual(evaluate('BTCUSDT', f).state, 'WAIT')

    def test_invalid_indicator(self):
        f = self.frames()
        f['15m'].loc[0, 'atr'] = np.nan
        with self.assertRaises(ValueError):
            evaluate('BTCUSDT', f)

    def test_expiry(self):
        d = evaluate('BTCUSDT', self.frames())
        self.assertEqual(d.closed_at, pd.Timestamp('2026-11-08T07:15Z'))
        self.assertEqual(d.expires_at, pd.Timestamp('2026-11-08T07:30Z'))

    def test_unavailable_is_not_a_short_signal(self):
        d = Decision('BTCUSDT', 'UNAVAILABLE', '网络不可用')
        s = format_decision(d)
        self.assertIn('无法判断', s)
        self.assertNotIn('做空信号触发', s)


class DataTests(unittest.TestCase):
    def setUp(self):
        self.as_of = pd.Timestamp('2026-11-08T07:16Z')
        ix = pd.date_range(end='2026-11-08T07:00Z', periods=300, freq='15min')
        self.frame = pd.DataFrame(dict(open=100., high=102., low=99., close=101., volume=10.), index=ix)
        self.frame['close_time'] = ix + pd.Timedelta(minutes=15) - pd.Timedelta(milliseconds=1)

    def test_valid(self):
        self.assertEqual(len(validate_frame(self.frame, '15m', self.as_of)), 300)

    def test_stale(self):
        with self.assertRaisesRegex(ValueError, '最新'):
            validate_frame(self.frame.iloc[:-1], '15m', self.as_of)

    def test_missing(self):
        with self.assertRaisesRegex(ValueError, '缺口'):
            validate_frame(self.frame.drop(self.frame.index[-5]), '15m', self.as_of)

    def test_short_history(self):
        with self.assertRaisesRegex(ValueError, '不足'):
            validate_frame(self.frame.tail(100), '15m', self.as_of)

    def test_bad_prices(self):
        self.frame.loc[self.frame.index[-1], 'high'] = 95.
        with self.assertRaises(ValueError):
            validate_frame(self.frame, '15m', self.as_of)

    def test_unfinished_excluded(self):
        future = self.frame.tail(1).copy()
        future.index += pd.Timedelta(minutes=15)
        future['close_time'] += pd.Timedelta(minutes=15)
        full = pd.concat([self.frame, future])
        self.assertEqual(len(validate_frame(full, '15m', self.as_of)), 300)


if __name__ == '__main__':
    unittest.main()
