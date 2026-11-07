import pandas as pd
import numpy as np
import statsmodels.api as sm

"""
Smart Beta and Factor Investing Case Study
"""

def performance_summary(returns, periods = 12):
    """
    Annualized univariate statistics for a set of excess return series.

    Used in sections 2.1 and 2.2

    Args:
    - returns (pd.DataFrame): excess returns, one column per asset or factor
    - periods (int): periods per year, 12 for monthly data

    Returns (pd.DataFrame): Mean, Volatility and Sharpe for each column, all annualized
    """
    mean = returns.mean() * periods
    vol = returns.std() * np.sqrt(periods)

    return pd.DataFrame({"Mean": mean,
                         "Volatility": vol,
                         "Sharpe": mean / vol})


def tangency_weights(returns):
    """
    Tangency portfolio weights from the sample mean and covariance of excess returns, w ∝ Σ⁻¹μ, scaled to sum to one.

    Used in section 2.4

    Args:
    - returns (pd.DataFrame): excess returns, one column per asset or factor

    Returns (pd.Series): the tangency weights, indexed by column name
    """
    mu = returns.mean()
    cov = returns.cov()

    raw = np.linalg.solve(cov, mu)

    return pd.Series(raw / raw.sum(), index = returns.columns)


def time_series_test(assets, factors, periods = 12):
    """
    Time-series test of a linear factor pricing model: regress each asset's excess return on the factors with an
    intercept. If the model prices the assets, every alpha is zero.

    Used in sections 3.1, 3.2, 3.3 and 3.5

    Args:
    - assets (pd.DataFrame): excess returns of the test assets, one column per asset
    - factors (pd.DataFrame): excess returns of the factors, on the same dates
    - periods (int): periods per year used to annualize alpha

    Returns (pd.DataFrame): one row per asset with the annualized Alpha, the factor betas and R-squared
    """
    X = sm.add_constant(factors)

    results = {}
    for asset in assets.columns:
        model = sm.OLS(assets[asset], X, missing = "drop").fit()

        row = {"Alpha": model.params["const"] * periods}
        row.update(model.params.drop("const"))
        row["R-squared"] = model.rsquared

        results[asset] = row

    return pd.DataFrame(results).T


def cross_sectional_test(assets, betas, periods = 12, intercept = True):
    """
    Cross-sectional test of a linear factor pricing model: regress the assets' mean excess returns on their
    time-series betas. The slopes are the estimated factor premia and the residuals are the pricing errors.

    Used in section 3.6

    Args:
    - assets (pd.DataFrame): excess returns of the test assets, one column per asset
    - betas (pd.DataFrame): time-series betas, one row per asset and one column per factor
    - periods (int): periods per year used to annualize the premia and residuals
    - intercept (bool): whether the cross-sectional regression includes an intercept

    Returns (tuple): the annualized premia (pd.Series, including the intercept when estimated) and the annualized
    residuals (pd.Series, one per asset)
    """
    y = assets.mean() * periods
    X = sm.add_constant(betas) if intercept else betas

    model = sm.OLS(y, X).fit()

    return model.params, model.resid


"""
AQR Momentum Strategy Case Study
"""

def momentum_summary(returns, factors, periods = 12):
    """
    Annualized performance stats for a set of momentum strategies, plus skewness and correlation to the market and
    value factors (the columns of Tables 1-4).

    Used in sections 2.1, 2.2, 2.3 and 2.4

    Args:
    - returns (pd.DataFrame): monthly strategy returns, one column per strategy
    - factors (pd.DataFrame): monthly factor excess returns with "MKT" and "HML" columns, on the same dates
    - periods (int): periods per year, 12 for monthly data

    Returns (pd.DataFrame): Mean, Volatility, Sharpe, Skewness, Corr. to MKT and Corr. to HML for each column
    """
    summary = performance_summary(returns, periods)
    summary["Skewness"] = returns.skew()
    summary["Corr. to MKT"] = returns.corrwith(factors["MKT"])
    summary["Corr. to HML"] = returns.corrwith(factors["HML"])

    return summary
