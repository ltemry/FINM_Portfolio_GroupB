import numpy as np
import pandas as pd

def annualize_stats(mean, vol, periods = 12):
    """
    Annualize mean return and volatility. Use periods = 12 for monthly data and periods = 252 for daily data.
    """
    ann_mean = mean * periods
    ann_vol = vol * np.sqrt(periods)

    return ann_mean, ann_vol


def max_drawdown_stats(returns):
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


def tail_stats(returns, level = 0.05):
    """
    Skewness and empirical VaR / CVaR at the given level for each column of total returns.
    """
    return pd.DataFrame({"Skewness": returns.skew(),
                         f"VaR ({level})": returns.quantile(level),
                         f"CVaR ({level})": returns.apply(lambda x: x[x <= x.quantile(level)].mean())})


def performance_stats(returns, rf, periods = 252, level = 0.05):
    """
    Summary statistics for each column of total returns. Mean, volatility, skewness, VaR, CVaR and drawdowns
    use total returns; the Sharpe ratio uses returns in excess of rf over the same dates.
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
    """
    return (1 + returns).groupby(returns.index.year).prod(min_count = 1) - 1


def regression_stats(y, X, periods = 252, intercept = True):
    """
    OLS of y on the columns of X over their common dates. Returns the betas, the annualized intercept with its
    t-statistic, R-squared and the annualized tracking error (residual volatility).
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
    """
    return pd.Series({col: 1 / (1 - regression_stats(X[col], X.drop(columns = col))["R-squared"]) for col in X.columns})


def rolling_regression(y, X, window = 252, step = 21, periods = 252):
    """
    Re-run regression_stats on a trailing window of `window` observations, stepped forward `step` observations
    at a time over the common dates of y and X. Each row is labeled by the last date in its window.
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
    Out-of-sample replica of y: fit OLS of y on X over a trailing `window` of observations, apply the fitted
    coefficients (including the intercept, if fitted) to the next `step` observations of X, then roll forward.
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
    Time-series momentum factor from the columns of excess returns. Each asset is held long or short by the sign
    of its trailing `lookback`-day excess return, scaled to `target_vol` by its trailing `vol_window`-day volatility,
    with both known at the previous close. Returns the equal-weighted average across assets.
    """
    signal = np.sign(excess.rolling(lookback).sum().shift(1))
    vol = excess.rolling(vol_window).std().shift(1) * np.sqrt(252)

    return (signal * target_vol / vol * excess).mean(axis = 1, skipna = False)


def block_r_squared(y, X, block = 63):
    """
    Adjusted R-squared of y on X fitted separately within each non-overlapping block of `block` observations.
    """
    import statsmodels.api as sm

    data = pd.concat([y, X], axis = 1).dropna()
    regressors = sm.add_constant(data[X.columns])

    return pd.Series({data.index[end - 1]: sm.OLS(data[y.name].iloc[end - block:end], regressors.iloc[end - block:end]).fit().rsquared_adj
                      for end in range(block, len(data) + 1, block)})


def inverse_variance_weights(cov):
    """
    Weights proportional to 1 / sigma_i^2, summing to one.
    """
    inv = 1 / np.diag(cov)
    return pd.Series(inv / inv.sum(), index = cov.index)


def inverse_vol_weights(cov):
    """
    Weights proportional to 1 / sigma_i, summing to one.
    """
    inv = 1 / np.sqrt(np.diag(cov))
    return pd.Series(inv / inv.sum(), index = cov.index)


def erc_weights(cov):
    """
    Equal-risk-contribution weights, summing to one. Solves the convex problem
    min 0.5 y' cov y - sum(log y) over y > 0, whose solution has y_i (cov y)_i = 1 for every i, then rescales.
    """
    from scipy.optimize import minimize

    sigma = cov.to_numpy()
    n = len(sigma)
    x0 = 1 / np.sqrt(np.diag(sigma))

    result = minimize(lambda y: 0.5 * y @ sigma @ y - np.log(y).sum(), x0,
                      jac = lambda y: sigma @ y - 1 / y,
                      bounds = [(1e-10, None)] * n, method = "L-BFGS-B", options = {"ftol": 1e-15, "gtol": 1e-12})

    return pd.Series(result.x / result.x.sum(), index = cov.index)


def risk_contributions(weights, cov):
    """
    Each asset's contribution to portfolio variance, w_i (cov w)_i, and its share of the total.
    """
    contributions = weights * (cov @ weights)
    return pd.DataFrame({"Weight": weights,
                         "Volatility": np.sqrt(np.diag(cov)),
                         "Risk Contribution": contributions,
                         "Share of Variance": contributions / contributions.sum()})


def month_end_weights(returns, rule, window = 252, start = None):
    """
    Weights set at each month-end close from the covariance of the trailing `window` daily returns, using `rule`
    (a function from a covariance matrix to weights). Only month-ends with a full window are kept, and only from
    `start` on if given.
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
    Daily total returns of a portfolio rebalanced to `weights` at each month-end close (index of `weights`) and held
    without trading until the next rebalance, so positions drift with returns. Returns the daily portfolio return and
    the weights held at the start of each day.
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
    Portfolio reset at each month-end close (index of `weights`) to positions of leverage x weights, as fractions
    of net asset value, with 1 - leverage in cash earning (or, when negative, borrowing at) rf. Positions are held
    without trading until the next reset, so both the weights and the leverage drift. Returns the daily return,
    the positions held at the start of each day, and the one-way turnover at each reset after the first,
    half the sum of absolute position changes.
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
    Rolling historical-simulation VaR: the forecast for day t is the `level` quantile of the `window` returns
    through t - 1, so forecasts begin after a `window`-day burn-in.
    """
    return returns.rolling(window).quantile(level).shift(1)


def ewma_volatility(returns, lam = 0.97, seed = 21):
    """
    Zero-mean EWMA volatility forecast, sigma_t^2 = lam sigma_{t-1}^2 + (1 - lam) r_{t-1}^2. sigma^2 is seeded with
    the variance of the first `seed` returns, which is the forecast for day seed + 1, and the recursion runs from there.
    """
    returns = returns.dropna()
    variance = pd.Series(np.nan, index = returns.index)
    variance.iloc[seed] = returns.iloc[:seed].var()

    for t in range(seed + 1, len(returns)):
        variance.iloc[t] = lam * variance.iloc[t - 1] + (1 - lam) * returns.iloc[t - 1] ** 2

    return np.sqrt(variance)


def normal_var_cvar(vol, level = 0.05):
    """
    One-day VaR and CVaR at `level` of a zero-mean normal return with volatility `vol`, both as returns (negative).
    """
    from scipy.stats import norm

    z = norm.ppf(level)
    return z * vol, -norm.pdf(z) / level * vol


def breach_stats(returns, var, windows):
    """
    Share of days whose return falls below the VaR forecast, over all days with a forecast and within each window
    in `windows` ({label: (start, end)}), with the number of breaches and of forecast days. A window with no forecasts
    is left blank.
    """
    data = pd.concat([returns.rename("Return"), var.rename("VaR")], axis = 1).dropna()
    samples = {"Full sample": data, **{label: data.loc[start:end] for label, (start, end) in windows.items()}}

    return pd.DataFrame({label: {"Breach Rate": (sample["Return"] < sample["VaR"]).mean() if len(sample) else np.nan,
                                 "Breaches": (sample["Return"] < sample["VaR"]).sum() if len(sample) else np.nan,
                                 "Forecast Days": len(sample)}
                         for label, sample in samples.items()}).T
