import functools

import decimal
import pytest
import numpy as np
from decimal import Decimal

import astropy.units as u
import astropy._erfa as erfa
from astropy.time import Time, TimeDelta
from astropy.time.utils import day_frac, two_sum
from astropy.utils import iers
from astropy.utils.exceptions import ErfaWarning

allclose_jd = functools.partial(np.allclose, rtol=2. ** -52, atol=0)
allclose_jd2 = functools.partial(np.allclose, rtol=2. ** -52,
                                 atol=2. ** -52)  # 20 ps atol
allclose_sec = functools.partial(np.allclose, rtol=2. ** -52,
                                 atol=2. ** -52 * 24 * 3600)  # 20 ps atol

tiny = 2. ** -52
dt_tiny = TimeDelta(tiny, format='jd')


def test_abs_jd2_always_less_than_half():
    """Make jd2 approach +/-0.5, and check that it doesn't go over."""
    t1 = Time(2400000.5, [-tiny, +tiny], format='jd')
    assert np.all(t1.jd1 % 1 == 0)
    assert np.all(abs(t1.jd2) < 0.5)
    t2 = Time(2400000., [[0.5-tiny, 0.5+tiny],
                         [-0.5-tiny, -0.5+tiny]], format='jd')
    assert np.all(t2.jd1 % 1 == 0)
    assert np.all(abs(t2.jd2) < 0.5)


def test_addition():
    """Check that an addition at the limit of precision (2^-52) is seen"""
    t = Time(2455555., 0.5, format='jd', scale='utc')

    t_dt = t + dt_tiny
    assert t_dt.jd1 == t.jd1 and t_dt.jd2 != t.jd2

    # Check that the addition is exactly reversed by the corresponding
    # subtraction
    t2 = t_dt - dt_tiny
    assert t2.jd1 == t.jd1 and t2.jd2 == t.jd2


def test_mult_div():
    """Test precision with multiply and divide"""
    dt_small = 6 * dt_tiny
    # pick a number that will leave remainder if divided by 6.
    dt_big = TimeDelta(20000., format='jd')
    dt_big_small_by_6 = (dt_big + dt_small) / 6.
    dt_frac = dt_big_small_by_6 - TimeDelta(3333., format='jd')
    assert allclose_jd2(dt_frac.jd2, 0.33333333333333354)


def test_init_variations():
    """Check that 3 ways of specifying a time + small offset are equivalent"""
    dt_tiny_sec = dt_tiny.jd2 * 86400.
    t1 = Time(1e11, format='cxcsec') + dt_tiny
    t2 = Time(1e11, dt_tiny_sec, format='cxcsec')
    t3 = Time(dt_tiny_sec, 1e11, format='cxcsec')
    assert t1.jd1 == t2.jd1
    assert t1.jd2 == t3.jd2
    assert t1.jd1 == t2.jd1
    assert t1.jd2 == t3.jd2


def test_precision_exceeds_64bit():
    """
    Check that Time object really holds more precision than float64 by looking
    at the (naively) summed 64-bit result and asserting equality at the
    bit level.
    """
    t1 = Time(1.23456789e11, format='cxcsec')
    t2 = t1 + dt_tiny
    assert t1.jd == t2.jd


def test_through_scale_change():
    """Check that precision holds through scale change (cxcsec is TT)"""
    t0 = Time(1.0, format='cxcsec')
    t1 = Time(1.23456789e11, format='cxcsec')
    dt_tt = t1 - t0
    dt_tai = t1.tai - t0.tai
    assert allclose_jd(dt_tt.jd1, dt_tai.jd1)
    assert allclose_jd2(dt_tt.jd2, dt_tai.jd2)


def test_iso_init():
    """Check when initializing from ISO date"""
    t1 = Time('2000:001:00:00:00.00000001', scale='tai')
    t2 = Time('3000:001:13:00:00.00000002', scale='tai')
    dt = t2 - t1
    assert allclose_jd2(dt.jd2, 13. / 24. + 1e-8 / 86400. - 1.0)


def test_jd1_is_mult_of_one():
    """
    Check that jd1 is a multiple of 1.
    """
    t1 = Time('2000:001:00:00:00.00000001', scale='tai')
    assert np.round(t1.jd1) == t1.jd1
    t1 = Time(1.23456789, 12345678.90123456, format='jd', scale='tai')
    assert np.round(t1.jd1) == t1.jd1


def test_precision_neg():
    """
    Check precision when jd1 is negative.  This used to fail because ERFA
    routines use a test like jd1 > jd2 to decide which component to update.
    It was updated to abs(jd1) > abs(jd2) in erfa 1.6 (sofa 20190722).
    """
    t1 = Time(-100000.123456, format='jd', scale='tt')
    assert np.round(t1.jd1) == t1.jd1
    t1_tai = t1.tai
    assert np.round(t1_tai.jd1) == t1_tai.jd1


def test_precision_epoch():
    """
    Check that input via epoch also has full precision, i.e., against
    regression on https://github.com/astropy/astropy/pull/366
    """
    t_utc = Time(range(1980, 2001), format='jyear', scale='utc')
    t_tai = Time(range(1980, 2001), format='jyear', scale='tai')
    dt = t_utc - t_tai
    assert allclose_sec(dt.sec, np.round(dt.sec))


def test_leap_seconds_rounded_correctly():
    """Regression tests against #2083, where a leap second was rounded
    incorrectly by the underlying ERFA routine."""
    with iers.conf.set_temp('auto_download', False):
        t = Time(['2012-06-30 23:59:59.413',
                  '2012-07-01 00:00:00.413'], scale='ut1', precision=3).utc
        assert np.all(t.iso == np.array(['2012-06-30 23:59:60.000',
                                         '2012-07-01 00:00:00.000']))
    # with the bug, both yielded '2012-06-30 23:59:60.000'


def test_two_sum_simple():
    with decimal.localcontext(decimal.Context(prec=40)):
        i, f = 65536, 3.637978807091714e-12
        a = Decimal(i) + Decimal(f)
        s, r = two_sum(i, f)
        b = Decimal(s) + Decimal(r)
        assert (abs(a-b)*u.day).to(u.ns) < 1*u.ns


def test_day_frac_harmless():
    with decimal.localcontext(decimal.Context(prec=40)):
        i, f = 65536, 3.637978807091714e-12
        a = Decimal(i) + Decimal(f)
        i_d, f_d = day_frac(i, f)
        a_d = Decimal(i_d) + Decimal(f_d)
        assert (abs(a-a_d)*u.day).to(u.ns) < 1*u.ns


def test_day_frac_idempotent():
    i, f = 65536, 3.637978807091714e-12
    i_d, f_d = day_frac(i, f)
    assert i_d, f_d == day_frac(i_d, f_d)


def test_mjd_initialization_precise():
    i, f = 65536, 3.637978807091714e-12  # Found using hypothesis
    t = Time(val=i, val2=f, format="mjd", scale="tai")
    jd1, jd2 = day_frac(i + erfa.DJM0, f)
    jd1_t, jd2_t = day_frac(t.jd1, t.jd2)
    assert (abs((jd1-jd1_t) + (jd2-jd2_t))*u.day).to(u.ns) < 1*u.ns


def test_conversion_preserves_jd1_jd2_invariant():
    """Conversion can leave jd1 not an integer"""
    scale1 = 'tai'
    scale2 = 'tcb'
    jd1, jd2 = 0., 0.
    t = Time(jd1, jd2, scale=scale1, format="jd")
    with pytest.warns(
            ErfaWarning,
            match=r'ERFA function "taiutc" yielded 1 of "dubious year'):
        t2 = getattr(t, scale2)
    assert t2.jd1 % 1 == 0
    assert abs(t2.jd2) <= 0.5
    assert abs(t2.jd2) < 0.5 or t2.jd1 % 2 == 0


def test_conversion_preserves_jd1_jd2_invariant_2():
    """Conversion can leave abs(jd2)>0.5"""
    scale1 = 'tai'
    scale2 = 'tcb'
    jd1, jd2 = (2441316.5, 0.0)
    t = Time(jd1, jd2, scale=scale1, format="jd")
    t2 = getattr(t, scale2)
    assert t2.jd1 % 1 == 0
    assert abs(t2.jd2) <= 0.5
    assert abs(t2.jd2) < 0.5 or t2.jd1 % 2 == 0
