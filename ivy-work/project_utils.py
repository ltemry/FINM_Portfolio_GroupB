import numpy as np
import pandas as pd

def annualize_stats(mean, vol, periods = 12):
    """
    Annualize a mean return and a volatility: the mean scales by the number of periods a year, the volatility by its square root.

    Used in sections 1.1, 1.2, 4.2, 4.3, 4.4, 6.1, 6.2, 7.2 and 7.3 (through performance_stats and regime_stats)

    Args:
    - mean (float or pd.Series): mean return per period
    - vol (float or pd.Series): standard deviation of returns per period
    - periods (int): periods per year, 12 for monthly data and 252 for daily data

    Returns (tuple): the annualized mean and the annualized volatility, each the same type as the inputs
    """
    ann_mean = mean * periods
    ann_vol = vol * np.sqrt(periods)

    return ann_mean, ann_vol


def max_drawdown_stats(returns):
    """
    Maximum drawdown of one return series, with its peak, trough and recovery dates. Wealth starts at 1 on the day
    before the first return, so a loss on the first day counts.

    Used in sections 1.1, 1.2, 4.2, 4.3, 4.4, 7.2 and 7.3 (through performance_stats)

    Args:
    - returns (pd.Series): daily total returns; missing values are dropped

    Returns (pd.Series): Max Drawdown, Peak Date, Trough Date and Recovery Date (NaT if wealth has not regained the peak)
    """
    returns = returns.dropna()

    #calculate cumulative wealth and running maximum
    wealth = (1 + returns).cumprod()
    wealth = pd.concat([pd.Series([1.0], index = [returns.index[0] - pd.Timedelta(days = 1)]), wealth])

    running_max = wealth.cummax()

    drawdowns = wealth / running_max - 1

    trough_date = drawdowns.idxmin()
    peak_date = wealth.loc[:trough_date].idxmax()

    recovery = wealth.loc[trough_date:]
    recovery = recovery[recovery >= wealth.loc[peak_date]]
    recovery_date = recovery.index[0] if not recovery.empty else pd.NaT

    return pd.Series({"Max Drawdown": drawdowns.loc[trough_date],
                      "Peak Date": peak_date,
                      "Trough Date": trough_date,
                      "Recovery Date": recovery_date})


def empirical_var(returns, level = 0.05):
    """
    Empirical VaR as the lower quantile of the lecture notes, inf{x : F(x) >= level}: the ceil(level x N)-th lowest return.

    Used in sections 1.1, 1.2, 4.2, 4.3, 4.4, 7.2 and 7.3 (through tail_stats) and 5.1 (through historical_var)

    Args:
    - returns (np.ndarray or pd.Series): returns; missing values are dropped
    - level (float): tail probability, e.g. 0.05

    Returns (float): the VaR, as a return (negative)
    """
    import math

    x = np.sort(np.asarray(returns, dtype = float))
    x = x[~np.isnan(x)]
    return x[math.ceil(level * len(x)) - 1]


def empirical_cvar(returns, level = 0.05):
    """
    Empirical CVaR as in the lecture notes: the mean of the worst level x N returns, counting a fraction a of the next one
    when level x N is not an integer, (sum of the k lowest + a x the (k+1)-th lowest) / (level x N).

    Used in sections 1.1, 1.2, 4.2, 4.3, 4.4, 7.2 and 7.3 (through tail_stats)

    Args:
    - returns (np.ndarray or pd.Series): returns; missing values are dropped
    - level (float): tail probability, e.g. 0.05

    Returns (float): the CVaR, as a return (negative)
    """
    import math

    x = np.sort(np.asarray(returns, dtype = float))
    x = x[~np.isnan(x)]
    k = math.floor(level * len(x))
    a = level * len(x) - k

    return (x[:k].sum() + (a * x[k] if a > 0 else 0)) / (level * len(x))


def tail_stats(returns, level = 0.05):
    """
    Skewness and empirical VaR and CVaR of each column of returns, using the lecture notes' lower-quantile VaR and tail-mean CVaR.

    Used in sections 1.1, 1.2, 4.2, 4.3, 4.4, 7.2 and 7.3 (through performance_stats)

    Args:
    - returns (pd.DataFrame): total returns, one column per series
    - level (float): tail probability for VaR and CVaR, e.g. 0.05

    Returns (pd.DataFrame): one row per column with Skewness, VaR (level) and CVaR (level), the last two as returns
    """
    return pd.DataFrame({"Skewness": returns.skew(),
                         f"VaR ({level})": returns.apply(lambda x: empirical_var(x, level)),
                         f"CVaR ({level})": returns.apply(lambda x: empirical_cvar(x, level))})


def performance_stats(returns, rf, periods = 252, level = 0.05):
    """
    Summary statistics for each column of total returns. Mean, volatility, skewness, VaR, CVaR and drawdowns use
    total returns; the Sharpe ratio uses returns in excess of rf over the same dates.

    Used in sections 1.1, 1.2, 4.2, 4.3, 4.4, 7.2 and 7.3

    Args:
    - returns (pd.DataFrame): total returns, one column per series
    - rf (pd.Series): risk-free (SHV) returns on the same dates
    - periods (int): periods per year, 252 for daily data
    - level (float): tail probability for VaR and CVaR

    Returns (pd.DataFrame): one row per column with First Return, Annualized Mean, Annualized Volatility, Sharpe Ratio,
    Skewness, VaR, CVaR, Max Drawdown, Peak Date, Trough Date and Recovery Date
    """
    excess = returns.sub(rf, axis = 0)

    ann_mean, ann_vol = annualize_stats(returns.mean(), returns.std(), periods)
    sharpe = excess.mean() / excess.std() * np.sqrt(periods)

    stats = pd.DataFrame({"First Return": returns.apply(pd.Series.first_valid_index),
                          "Annualized Mean": ann_mean,
                          "Annualized Volatility": ann_vol,
                          "Sharpe Ratio": sharpe})

    drawdowns = returns.apply(max_drawdown_stats).T

    return pd.concat([stats, tail_stats(returns, level), drawdowns], axis = 1)


def calendar_year_returns(returns):
    """
    Compounded total return by calendar year for each column. Years with no data are left blank.

    Used in sections 1.1 and 4.2

    Args:
    - returns (pd.DataFrame): daily total returns with a DatetimeIndex

    Returns (pd.DataFrame): one row per year, one column per series
    """
    return (1 + returns).groupby(returns.index.year).prod(min_count = 1) - 1


def regression_stats(y, X, periods = 252, intercept = True):
    """
    OLS regression of y on the columns of X over their common dates.

    Used in sections 1.2, 2.1, 2.2, 2.4, 3.2, 3.3 and 4.4

    Args:
    - y (pd.Series): dependent returns, e.g. a fund's excess returns
    - X (pd.DataFrame or pd.Series): regressors, e.g. factor excess returns
    - periods (int): periods per year, used to annualize the intercept and tracking error
    - intercept (bool): whether to fit an intercept

    Returns (pd.Series): the betas; Alpha (annualized intercept) and Alpha t-stat if an intercept is fitted; R-squared;
    and Tracking Error (annualized residual volatility)
    """
    import statsmodels.api as sm

    X = X.to_frame() if isinstance(X, pd.Series) else X
    data = pd.concat([y, X], axis = 1).dropna()

    regressors = sm.add_constant(data[X.columns]) if intercept else data[X.columns]
    model = sm.OLS(data[y.name], regressors).fit()

    stats = model.params.drop("const", errors = "ignore")

    if intercept:
        stats["Alpha"] = model.params["const"] * periods
        stats["Alpha t-stat"] = model.tvalues["const"]

    stats["R-squared"] = model.rsquared
    stats["Tracking Error"] = model.resid.std() * np.sqrt(periods)

    return stats


def variance_inflation(X):
    """
    Variance inflation factor of each column of X: 1 / (1 - R-squared) from regressing it on the other columns.

    Used in section 2.1

    Args:
    - X (pd.DataFrame): candidate factors, one column each

    Returns (pd.Series): the variance inflation factor of each column
    """
    return pd.Series({col: 1 / (1 - regression_stats(X[col], X.drop(columns = col))["R-squared"]) for col in X.columns})


def rolling_regression(y, X, window = 252, step = 21, periods = 252):
    """
    Re-run regression_stats on a trailing window of observations, stepped forward a fixed number of observations at a
    time over the common dates of y and X. Each row is labeled by the last date in its window.

    Used in section 2.3

    Args:
    - y (pd.Series): dependent returns
    - X (pd.DataFrame): regressors
    - window (int): observations in each regression
    - step (int): observations between consecutive window ends
    - periods (int): periods per year, passed to regression_stats

    Returns (pd.DataFrame): one row per window with the betas, Alpha, Alpha t-stat, R-squared, Tracking Error and Sum of Betas
    """
    data = pd.concat([y, X], axis = 1).dropna()

    results = {}

    for end in range(window, len(data) + 1, step):
        sample = data.iloc[end - window:end]
        stats = regression_stats(sample[y.name], sample[X.columns], periods = periods)
        stats["Sum of Betas"] = stats[X.columns].sum()
        results[sample.index[-1]] = stats

    return pd.DataFrame(results).T


def oos_replication(y, X, window = 252, step = 21, intercept = True):
    """
    Out-of-sample replica of y: fit OLS of y on X over a trailing window, apply the fitted coefficients (including
    the intercept, if fitted) to the next step observations of X, then roll forward.

    Used in sections 3.1 and 3.2

    Args:
    - y (pd.Series): returns to replicate, e.g. a fund's excess returns
    - X (pd.DataFrame): replicating factor returns
    - window (int): observations in each fit
    - step (int): observations each fit is applied to before refitting
    - intercept (bool): whether to fit an intercept and keep it in the replica

    Returns (pd.Series): the replica's returns, starting after the first full window
    """
    import statsmodels.api as sm

    data = pd.concat([y, X], axis = 1).dropna()
    regressors = sm.add_constant(data[X.columns]) if intercept else data[X.columns]

    replica = []

    for start in range(window, len(data), step):
        model = sm.OLS(data[y.name].iloc[start - window:start], regressors.iloc[start - window:start]).fit()
        replica.append(regressors.iloc[start:start + step] @ model.params)

    return pd.concat(replica).rename(f"{y.name} replica")


def trend_factor(excess, lookback = 252, vol_window = 63, target_vol = 0.10):
    """
    Time-series momentum factor. Each asset is held long or short by the sign of its trailing excess return, scaled
    to a target volatility by its trailing volatility, with both known at the previous close.

    Used in section 3.2

    Args:
    - excess (pd.DataFrame): daily excess returns, one column per asset
    - lookback (int): days in the trailing return that sets the sign
    - vol_window (int): days in the trailing volatility estimate
    - target_vol (float): annualized volatility each asset is scaled to

    Returns (pd.Series): the equal-weighted average of the scaled asset positions' daily returns
    """
    signal = np.sign(excess.rolling(lookback).sum().shift(1))
    vol = excess.rolling(vol_window).std().shift(1) * np.sqrt(252)

    return (signal * target_vol / vol * excess).mean(axis = 1, skipna = False)


def block_r_squared(y, X, block = 63):
    """
    Adjusted R-squared of y on X fitted separately within each non-overlapping block of observations, so the betas
    are free to change from block to block.

    Used in section 3.2

    Args:
    - y (pd.Series): dependent returns
    - X (pd.DataFrame): regressors
    - block (int): observations in each block

    Returns (pd.Series): adjusted R-squared of each block, labeled by its last date
    """
    import statsmodels.api as sm

    data = pd.concat([y, X], axis = 1).dropna()
    regressors = sm.add_constant(data[X.columns])

    return pd.Series({data.index[end - 1]: sm.OLS(data[y.name].iloc[end - block:end], regressors.iloc[end - block:end]).fit().rsquared_adj
                      for end in range(block, len(data) + 1, block)})


def inverse_variance_weights(cov):
    """
    Weights proportional to 1 / sigma_i^2, summing to one.

    Used in section 4.1

    Args:
    - cov (pd.DataFrame): covariance matrix of asset returns

    Returns (pd.Series): one weight per asset
    """
    inv = 1 / np.diag(cov)
    return pd.Series(inv / inv.sum(), index = cov.index)


def inverse_vol_weights(cov):
    """
    Weights proportional to 1 / sigma_i, summing to one.

    Used in section 4.1

    Args:
    - cov (pd.DataFrame): covariance matrix of asset returns

    Returns (pd.Series): one weight per asset
    """
    inv = 1 / np.sqrt(np.diag(cov))
    return pd.Series(inv / inv.sum(), index = cov.index)


def erc_weights(cov, return_result = False):
    """
    Equal-risk-contribution weights, summing to one. Solves the convex problem min 0.5 y' cov y - sum(log y) over
    y > 0, whose solution has y_i (cov y)_i = 1 for every i, then rescales.

    Used in sections 4.1 and 4.2 (and 7.2 through the 4.2 weights)

    Args:
    - cov (pd.DataFrame): covariance matrix of asset returns
    - return_result (bool): also return the optimizer's result object, to check convergence

    Returns (pd.Series, or tuple): one weight per asset; with return_result, the weights and the scipy OptimizeResult
    """
    from scipy.optimize import minimize

    sigma = cov.to_numpy()
    n = len(sigma)
    x0 = 1 / np.sqrt(np.diag(sigma))

    result = minimize(lambda y: 0.5 * y @ sigma @ y - np.log(y).sum(), x0,
                      jac = lambda y: sigma @ y - 1 / y,
                      bounds = [(1e-10, None)] * n, method = "L-BFGS-B", options = {"ftol": 1e-15, "gtol": 1e-12})

    weights = pd.Series(result.x / result.x.sum(), index = cov.index)

    return (weights, result) if return_result else weights


def erc_convergence(returns, weights, window = 252):
    """
    Convergence check of ERC weights at every rebalance date. Re-solves each date from the same trailing covariance and
    reports the optimizer's status and the largest deviation of any asset's share of portfolio variance from 1/n.

    Used in section 4.1

    Args:
    - returns (pd.DataFrame): daily asset returns; dates with any missing value are dropped
    - weights (pd.DataFrame): ERC weights, indexed by the rebalance dates
    - window (int): trailing days in each covariance estimate, as when the weights were set

    Returns (pd.DataFrame): one row per rebalance date with Optimizer Success, Message, Iterations, Max Share Deviation
    (largest |share - 1/n|) and Max Weight Difference (re-solved against stored weights)
    """
    returns = returns[weights.columns].dropna()
    n = weights.shape[1]

    rows = {}
    for date, stored in weights.iterrows():
        cov = returns.loc[:date].iloc[-window:].cov()
        solved, result = erc_weights(cov, return_result = True)
        shares = risk_contributions(stored, cov)["Share of Variance"]

        rows[date] = {"Optimizer Success": bool(result.success),
                      "Message": str(result.message),
                      "Iterations": result.nit,
                      "Max Share Deviation": (shares - 1 / n).abs().max(),
                      "Max Weight Difference": (solved - stored).abs().max()}

    return pd.DataFrame(rows).T


def risk_contributions(weights, cov):
    """
    Each asset's contribution to portfolio variance, w_i (cov w)_i, and its share of the total.

    Used in section 4.1

    Args:
    - weights (pd.Series): portfolio weights
    - cov (pd.DataFrame): covariance matrix of asset returns

    Returns (pd.DataFrame): one row per asset with Weight, Volatility, Risk Contribution and Share of Variance
    """
    contributions = weights * (cov @ weights)
    return pd.DataFrame({"Weight": weights,
                         "Volatility": np.sqrt(np.diag(cov)),
                         "Risk Contribution": contributions,
                         "Share of Variance": contributions / contributions.sum()})


def month_end_weights(returns, rule, window = 252, start = None):
    """
    Weights set at each month-end close from the covariance of the trailing daily returns, using a weighting rule.
    Only month-ends with a full window are kept.

    Used in sections 4.1 and 4.2

    Args:
    - returns (pd.DataFrame): daily asset returns; dates with any missing value are dropped
    - rule (callable): function from a covariance matrix (pd.DataFrame) to weights (pd.Series)
    - window (int): trailing days in each covariance estimate
    - start (str or None): first month-end to keep, if given

    Returns (pd.DataFrame): one row of weights per month-end, indexed by the month-end date
    """
    returns = returns.dropna()
    month_ends = returns.groupby(returns.index.to_period("M")).apply(lambda x: x.index[-1])
    #the last date in the data is not a month-end unless a following date exists
    month_ends = month_ends[month_ends < returns.index[-1]]

    weights = {}
    for date in month_ends:
        trailing = returns.loc[:date].iloc[-window:]
        if len(trailing) == window and (start is None or date >= pd.Timestamp(start)):
            weights[date] = rule(trailing.cov())

    return pd.DataFrame(weights).T


def buy_and_hold_backtest(returns, weights):
    """
    Daily returns of a portfolio rebalanced to the target weights at each month-end close and held without trading
    until the next rebalance, so the weights drift with returns.

    Used in sections 4.1 and 4.2

    Args:
    - returns (pd.DataFrame): daily asset returns
    - weights (pd.DataFrame): target weights, indexed by the rebalance dates

    Returns (tuple): the daily portfolio return (pd.Series) and the weights held at the start of each day (pd.DataFrame)
    """
    returns = returns.loc[returns.index > weights.index[0], weights.columns]

    held = []
    current = None
    for date, r in returns.iterrows():
        previous = returns.index[returns.index.get_loc(date) - 1] if date != returns.index[0] else weights.index[0]
        if previous in weights.index:
            current = weights.loc[previous]
        held.append(current.rename(date))
        grown = current * (1 + r)
        current = grown / grown.sum()

    held = pd.DataFrame(held)
    return (held * returns).sum(axis = 1), held


def levered_backtest(returns, weights, rf, leverage = 1.0):
    """
    Portfolio reset at each month-end close to positions of leverage x weights, as fractions of net asset value, with
    1 - leverage in cash earning (or, when negative, borrowing at) rf. Positions are held without trading until the next
    reset, so both the weights and the leverage drift.

    Used in sections 4.3 and 7.2

    Args:
    - returns (pd.DataFrame): daily asset returns
    - weights (pd.DataFrame): target weights or positions, indexed by the reset dates
    - rf (pd.Series): daily cash (SHV) returns
    - leverage (float): multiple applied to the weights at each reset

    Returns (tuple): the daily return (pd.Series), the positions held at the start of each day (pd.DataFrame), and the one-way
    turnover at each reset after the first, half the sum of absolute position changes (pd.Series)
    """
    returns = returns.loc[returns.index > weights.index[0], weights.columns]
    rf = rf.loc[returns.index]

    positions, port, turnover = [], [], {}
    current = leverage * weights.iloc[0]
    reset_dates = set(weights.index)

    for i, (date, r) in enumerate(returns.iterrows()):
        previous = returns.index[i - 1] if i > 0 else weights.index[0]
        if previous in reset_dates and i > 0:
            target = leverage * weights.loc[previous]
            turnover[previous] = 0.5 * (target - current).abs().sum()
            current = target

        cash = 1 - current.sum()
        day_return = (current * r).sum() + cash * rf[date]

        positions.append(current.rename(date))
        port.append(day_return)

        current = current * (1 + r) / (1 + day_return)

    return pd.Series(port, index = returns.index), pd.DataFrame(positions), pd.Series(turnover)


def historical_var(returns, window = 252, level = 0.05):
    """
    Rolling historical-simulation VaR. The forecast for day t is the lower quantile (empirical_var) of the trailing window
    of returns through t - 1, so forecasts begin after a full window.

    Used in section 5.1

    Args:
    - returns (pd.Series): daily total returns
    - window (int): trailing days in each estimate
    - level (float): tail probability, e.g. 0.05

    Returns (pd.Series): the VaR forecast for each day, as a return (negative)
    """
    return returns.rolling(window).apply(lambda x: empirical_var(x, level), raw = True).shift(1)


def ewma_volatility(returns, lam = 0.97, seed = 21):
    """
    Zero-mean EWMA volatility forecast, sigma_t^2 = lam sigma_{t-1}^2 + (1 - lam) r_{t-1}^2. sigma^2 is seeded with the
    variance of the first seed returns, which is the forecast for day seed + 1, and the recursion runs from there.

    Used in section 5.1

    Args:
    - returns (pd.Series): daily total returns; missing values are dropped
    - lam (float): decay factor
    - seed (int): number of initial returns used to seed the variance

    Returns (pd.Series): the daily volatility forecast, blank before the first forecast
    """
    returns = returns.dropna()
    variance = pd.Series(np.nan, index = returns.index)
    variance.iloc[seed] = returns.iloc[:seed].var()

    for t in range(seed + 1, len(returns)):
        variance.iloc[t] = lam * variance.iloc[t - 1] + (1 - lam) * returns.iloc[t - 1] ** 2

    return np.sqrt(variance)


def normal_var_cvar(vol, level = 0.05):
    """
    One-day VaR and CVaR of a zero-mean Normal return with the given volatility.

    Used in sections 5.1 and 5.2

    Args:
    - vol (float or pd.Series): volatility forecast
    - level (float): tail probability, e.g. 0.05

    Returns (tuple): VaR and CVaR, each the same type as vol and expressed as returns (negative)
    """
    from scipy.stats import norm

    z = norm.ppf(level)
    return z * vol, -norm.pdf(z) / level * vol


def breach_stats(returns, var, windows):
    """
    Share of days whose return falls below the VaR forecast, over all days with a forecast and within each window, with
    the number of breaches and of forecast days. A window with no forecasts is left blank.

    Used in section 5.1

    Args:
    - returns (pd.Series): daily total returns
    - var (pd.Series): VaR forecasts for the same days
    - windows (dict): {label: (start, end)} date windows

    Returns (pd.DataFrame): one row for the full sample and one per window, with Breach Rate, Breaches and Forecast Days
    """
    data = pd.concat([returns.rename("Return"), var.rename("VaR")], axis = 1).dropna()
    samples = {"Full sample": data, **{label: data.loc[start:end] for label, (start, end) in windows.items()}}

    return pd.DataFrame({label: {"Breach Rate": (sample["Return"] < sample["VaR"]).mean() if len(sample) else np.nan,
                                 "Breaches": (sample["Return"] < sample["VaR"]).sum() if len(sample) else np.nan,
                                 "Forecast Days": len(sample)}
                         for label, sample in samples.items()}).T


def regime_stats(excess, regimes, periods = 12):
    """
    Annualized mean, volatility and Sharpe ratio of excess returns within each regime, aligned on dates. Periods without
    both a return and a regime label are dropped.

    Used in sections 6.1 and 6.2

    Args:
    - excess (pd.Series): excess returns, e.g. monthly
    - regimes (pd.Series): regime label for each period
    - periods (int): periods per year, 12 for monthly data

    Returns (pd.DataFrame): one row per regime with Months, Annualized Mean, Annualized Volatility and Sharpe Ratio
    """
    data = pd.concat([excess.rename("Excess"), regimes.rename("Regime")], axis = 1).dropna()
    grouped = data.groupby("Regime", observed = True)["Excess"]

    mean, vol = annualize_stats(grouped.mean(), grouped.std(), periods = periods)

    return pd.DataFrame({"Months": grouped.count(),
                         "Annualized Mean": mean,
                         "Annualized Volatility": vol,
                         "Sharpe Ratio": mean / vol})


def regime_difference(excess, regimes, good, bad, periods = 12):
    """
    Difference in annualized mean excess return between a good and a bad regime, with its Welch t-statistic and the
    number of separate spells of the good regime (a run of consecutive periods counts once).

    Used in section 6.2

    Args:
    - excess (pd.Series): excess returns, e.g. monthly
    - regimes (pd.Series): regime label for each period
    - good (str): label of the regime hypothesized to be good
    - bad (str): label of the regime hypothesized to be bad
    - periods (int): periods per year, 12 for monthly data

    Returns (pd.Series): Mean Difference, t-stat and Good Spells
    """
    from scipy.stats import ttest_ind

    data = pd.concat([excess.rename("Excess"), regimes.rename("Regime")], axis = 1).dropna()
    good_returns = data.loc[data["Regime"] == good, "Excess"]
    bad_returns = data.loc[data["Regime"] == bad, "Excess"]
    in_good = (data["Regime"] == good).astype(int)

    return pd.Series({"Mean Difference": (good_returns.mean() - bad_returns.mean()) * periods,
                      "t-stat": ttest_ind(good_returns, bad_returns, equal_var = False).statistic,
                      "Good Spells": ((in_good == 1) & (in_good.shift(fill_value = 0) == 0)).sum()})


def trend_filtered_positions(returns, excess, weights, target_vol = 0.10, max_leverage = 2.0, window = 252, lookback = 252):
    """
    Month-end position targets for the 7.2 strategy, as fractions of net asset value. The weights are scaled by
    L = min(target_vol / forecast volatility, max_leverage), then any asset whose summed excess return over the trailing
    lookback days is not positive is set to zero, its share left in cash.

    Used in section 7.2

    Args:
    - returns (pd.DataFrame): daily asset returns, used for the covariance
    - excess (pd.DataFrame): daily asset excess returns, used for the trend filter
    - weights (pd.DataFrame): base weights (ERC), indexed by month-end
    - target_vol (float): annualized volatility target
    - max_leverage (float): cap on L
    - window (int): trailing days in the covariance estimate
    - lookback (int or None): trailing days in the trend filter; None turns the filter off

    Returns (tuple): the position targets (pd.DataFrame) and the leverage L set at each month-end before the filter (pd.Series)
    """
    returns = returns[weights.columns].dropna()
    excess = excess[weights.columns]

    positions, leverage = {}, {}
    for date, w in weights.iterrows():
        trailing = returns.loc[:date].iloc[-window:]
        forecast_vol = np.sqrt(w @ trailing.cov() @ w * 252)
        leverage[date] = min(target_vol / forecast_vol, max_leverage)

        in_trend = excess.loc[:date].iloc[-lookback:].sum() > 0 if lookback else pd.Series(True, index = w.index)
        positions[date] = leverage[date] * w * in_trend

    return pd.DataFrame(positions).T, pd.Series(leverage)


def net_of_costs(gross, positions, turnover, cost_per_turnover, borrow_spread, periods = 252):
    """
    Daily returns net of trading and financing costs. Trading costs are charged on the day after each month-end reset;
    financing costs accrue daily on the borrowed amount, the excess of gross exposure over net asset value.

    Used in sections 7.2 and 7.3

    Args:
    - gross (pd.Series): daily returns before costs
    - positions (pd.DataFrame): positions held at the start of each day, as fractions of net asset value
    - turnover (pd.Series): one-way turnover at each reset, indexed by the reset date
    - cost_per_turnover (float): cost per unit of one-way turnover, e.g. 0.001
    - borrow_spread (float): annual spread over the cash rate on the borrowed amount, e.g. 0.0075
    - periods (int): periods per year, 252 for daily data

    Returns (pd.Series): daily returns after costs
    """
    borrowed = (positions.abs().sum(axis = 1) - 1).clip(lower = 0)
    trading = turnover.reindex(gross.index).shift(1).fillna(0) * cost_per_turnover

    return gross - borrowed * borrow_spread / periods - trading


def criteria_check(returns, benchmark, rf, max_correlation = 0.80, periods = 252):
    """
    The four 7.1 criteria for one return series against a benchmark (60/40), over the dates where the series has returns.

    Used in section 7.4

    Args:
    - returns (pd.Series): daily total returns of the series being tested
    - benchmark (pd.Series): daily total returns of 60/40
    - rf (pd.Series): daily cash (SHV) returns
    - max_correlation (float): highest correlation with the benchmark that passes criterion 4
    - periods (int): periods per year, 252 for daily data

    Returns (pd.Series): Start and End dates; Sharpe and Hurdle; Max Drawdown and 60/40 Max Drawdown; 2022 Return and 60/40 2022
    Return (blank if 2022 is not fully covered); Correlation; and a pass flag for each criterion (1. Sharpe, 2. Drawdown,
    3. 2022, 4. Correlation)
    """
    data = pd.concat([returns.rename("Series"), benchmark.rename("Benchmark")], axis = 1).dropna()
    excess = data.sub(rf.loc[data.index], axis = 0)

    sharpe = excess.mean() / excess.std() * np.sqrt(periods)
    wealth = pd.concat([pd.DataFrame(1.0, index = [data.index[0] - pd.Timedelta(days = 1)], columns = data.columns), (1 + data).cumprod()])
    drawdown = (wealth / wealth.cummax() - 1).min()
    correlation = data["Series"].corr(data["Benchmark"])

    has_2022 = data.index[0] <= pd.Timestamp("2022-01-03") and data.index[-1] >= pd.Timestamp("2022-12-30")
    return_2022 = (1 + data.loc["2022"]).prod() - 1 if has_2022 else pd.Series(np.nan, index = data.columns)

    return pd.Series({"Start": data.index[0], "End": data.index[-1],
                      "Sharpe": sharpe["Series"], "Hurdle": correlation * sharpe["Benchmark"],
                      "1. Sharpe": sharpe["Series"] > correlation * sharpe["Benchmark"],
                      "Max Drawdown": drawdown["Series"], "60/40 Max Drawdown": drawdown["Benchmark"],
                      "2. Drawdown": drawdown["Series"] >= drawdown["Benchmark"],
                      "2022 Return": return_2022["Series"], "60/40 2022 Return": return_2022["Benchmark"],
                      "3. 2022": return_2022["Series"] >= return_2022["Benchmark"] if has_2022 else np.nan,
                      "Correlation": correlation,
                      "4. Correlation": correlation <= max_correlation})
