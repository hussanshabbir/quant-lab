MASTER BLUEPRINT — QUANT / HFT RESEARCH PROJECT

0. THE GOAL

The ultimate goal is:
Build a research and trading system capable of discovering, testing, executing, and continuously evaluating genuine market edges across global futures, FX, equities, rates, commodities, and cross-market relationships — starting with your own capital, proving profitability and robustness first, and only later considering turning it into a firm.

You are not currently trying to build the public firm.

The order is:
LEARN → COLLECT DATA → UNDERSTAND MARKETS → DISCOVER PATTERNS → TEST PATTERNS → BUILD MODELS → SIMULATE EXECUTION → PAPER/SHADOW → TRADE YOUR OWN CAPITAL → PROVE PROFITABILITY → SCALE → ONLY THEN CONSIDER FIRM

The immediate objective is not HFT for the sake of saying HFT. The immediate objective is: Find out what information actually predicts what, how long that information lasts, and whether it can be monetized after costs and execution.

1. THE ORIGINAL IDEA

Original hypothesis: Global markets open and close at different times. When one market transitions into another, highs, lows, ranges, liquidity and price behavior may carry information into the next market.

Refined: We are not assuming Asia high → London copies it → New York copies London. Instead, we are testing GLOBAL INFORMATION FLOW: Asia → FX/rates/index futures → Europe → European futures/FX/rates → New York → U.S. futures/cash equities/rates → next global session.

The real question: Does price discovery and liquidity migrate between markets in a predictable way?

2. WHAT WE HAVE ALREADY LEARNED

A. Markets aren't isolated — CME equity-index futures provide a nearly continuous futures market across the global trading day. Cash-market closures don't necessarily mean information flow stops. CME's historical-data infrastructure supports working at multiple levels: settlements, trades, top-of-book, market depth, MBO.

B. Asia isn't one session — Japan: JPX Nikkei futures DAY 08:45→15:40 JST (closing auction→15:45), NIGHT 17:00→05:55 JST (closing auction→06:00), plus pre-opening and auction mechanisms. "Asia close" isn't one universal moment.

C. Hong Kong has another structure — HSI futures: 09:15→12:00, 13:00→16:30, 17:00→03:00 next day. Morning, afternoon, after-hours rather than one continuous session.

D. Auctions matter — JPX and HKEX both use pre-open/closing auction periods (HKEX includes a randomized closing time). Need to model pre-open → auction → continuous trading separately.

3. THE CORE PRINCIPLE

RESEARCH → DATA → MODEL → EXECUTION → FEEDBACK → RISK → INFRASTRUCTURE → CONTINUOUS ADAPTATION

Underlying scientific loop: HYPOTHESIS → DATA → TEST → RESULT → VALIDATE → TRY TO DESTROY IT → SURVIVES? (NO→DROP / YES→PAPER→LIVE)

4. FULL PHASE MAP

PHASES 1–3 — FOUNDATION
Phase 1 — Global market understanding: learn exchanges/instruments/sessions/settlements/auctions/contract specs/participants across US, Europe, UK, Hong Kong, Japan, China, Australia, Singapore, India, Canada; equities, futures, FX, rates, commodities, options, crypto.
Phase 2 — Global timing architecture: master clock (UTC → exchange local time → session → auction → trading state). Handle DST, holidays, early closes, special/overnight sessions.
Phase 3 — Market structure/microstructure: bid/ask/spread/depth/queue/limit orders/market orders/cancellations/aggressor flow/auction/price discovery/slippage/market impact. Distinguish investing, swing trading, systematic trading, stat arb, algo trading, market making, HFT.

PHASES 4–10 — RESEARCH ENGINE
Phase 4 — Data Lab: hierarchy = Level 0 instrument/reference data, Level 1 OHLCV, Level 2 trades, Level 3 quotes, Level 4 order book/MBO. Sources: CME, NYSE, Nasdaq, JPX, HKEX, Eurex, FX data, macro data, news. CME DataMine is the official historical-data route.
Phase 5 — Time/session/contract engine: exchange calendar, session calendar, holiday calendar, DST engine, contract master, roll engine. Every observation gets UTC timestamp, local timestamp, exchange, instrument, contract, session, trading date.
Phase 6 — Feature/hypothesis engine: price, return, range, VWAP, volume, volatility, spread, depth, order imbalance, cross-market relationships, macro, calendar, session state.
Phase 7 — Backtest/statistics engine: event studies, predictive studies, trading simulations with fees/spread/slippage/latency/market impact. Then confidence intervals, bootstrap, permutation, multiple-testing correction, out-of-sample, walk-forward, Monte Carlo.
Phase 8 — Microstructure/execution engine: reconstruct order book, queue, fills, partial fills, cancellations, latency, adverse selection. Simulate actual execution.
Phase 9 — Paper/live research: historical → backtest → out-of-sample → shadow → paper → tiny live.
Phase 10 — Risk/adaptation: position limits, drawdown limits, loss limits, exposure, correlation, regime detection, drift detection, model versioning.

PHASES 11–20 — GLOBAL MARKET DISCOVERY
Phase 11 — Global session map: Tokyo, Hong Kong, Singapore, London, Frankfurt, New York, Chicago, Sydney and overlaps.
Phase 12 — Liquidity map: per-minute volume/spread/depth/trades/volatility/order arrival/cancellation — find when liquidity appears/disappears.
Phase 13 — Price-discovery map: which market moves first? Test NQ→ES, ZN→NQ, USDJPY→Nikkei, CNH→HSI, EURUSD→DAX, CL→CAD at ms/sec/min scales.
Phase 14 — Cross-market lead/lag: full LEADER→FOLLOWER matrix, never assuming direction.
Phase 15 — Session transition research: Asia→Europe, Europe→NY, NY→Asia using high/low/range/VWAP/close/volatility/volume.
Phase 16 — Opening auctions: pre-open, auction imbalance, indicative price, opening price, first trade, opening range, post-open response.
Phase 17 — Closing auctions: pre-close, closing imbalance, auction, closing price, after-hours, next-session response.
Phase 18 — Overnight → cash: ES overnight → U.S. cash open. Study overnight high/low/VWAP/gap/range/volatility.
Phase 19 — FX session research: Sydney/Tokyo/HK/London/NY/London-NY overlap for EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, USDCNH.
Phase 20 — Futures basis: futures vs spot including basis, fair value, rates, dividends, expiry.

PHASES 21–30 — ALPHA & EXECUTION
Phase 21 — Macro-event engine: CPI, PCE, PPI, NFP, GDP, ISM, PMI, FOMC, ECB, BoE, BoJ, EIA, OPEC, China data — with consensus/actual/prior/revision/surprise/timestamp.
Phase 22 — News/speech engine: central-bank speeches, government announcements, earnings, geopolitical events, emergency announcements. Measure expected/actual/surprise/first market/second market/reaction duration.
Phase 23 — Volatility regimes: very low/low/normal/high/extreme.
Phase 24 — Liquidity regimes: deep/normal/thin/extremely thin.
Phase 25 — Order-flow engine: aggressor imbalance, book imbalance, trade intensity, cancellation intensity, depth, spread, queue.
Phase 26 — Market-making engine: test EV = spread capture − adverse selection − fees − inventory risk.
Phase 27 — Momentum/mean-reversion engine: classify edges as momentum, mean reversion, breakout, liquidity reversal, event response, cross-market arbitrage.
Phase 28 — Statistical arbitrage: ES/NQ, ES/RTY, DAX/EuroStoxx, Nikkei/USDJPY, HSI/CNH, EURUSD/DAX, CL/CAD, GC/USD, ZN/NQ using cointegration, stationarity, half-life, dynamic hedge ratios, z-scores, regime stability.
Phase 29 — Execution edge: ExecutionAlpha = TheoreticalPnL − RealizedPnL.
Phase 30 — Latency sensitivity: run strategy with artificial delays (0/1/5/10/25/50/100/250/500ms/1s) to determine if it's HFT, short-term algo, or slower systematic.

PHASES 31–35 — VALIDATION
Phase 31 — Adversarial testing: 2x/5x fees, slippage, spread, latency; remove best/worst trades; perturb entries/exits.
Phase 32 — Data-snooping defense: track hypothesis ID, creation date, dataset, parameters, features, result. Prevent overfitting, multiple-testing illusion, look-ahead bias, selection bias.
Phase 33 — Live shadow: real-time signal/decision/hypothetical order/hypothetical fill/markout, no capital.
Phase 34 — Strategy selection: rank by edge, stability, liquidity, execution, drawdown, complexity, capacity, regime dependency.
Phase 35 — First real result: the gate we're currently approaching. Don't declare victory until actual historical bars produce a result.

PHASES 36–45 — DEEP MARKET BEHAVIOR
Phase 36 — Event-clock synchronization: separate exchange timestamp, receive timestamp, our timestamp — critical for HFT.
Phase 37 — Cross-asset impulse response: measure rates→FX→equities, FX→Asia, commodities→currencies for macro/news/large moves.
Phase 38 — Information half-life: how long a signal remains useful (microsecond/millisecond/second/minute/hour classes).
Phase 39 — Price-discovery reversals: A moves → B follows → A reverses → B lags.
Phase 40 — Liquidity vacuums: depth collapse, spread explosion, cancellation surge, trade-intensity spike.
Phase 41 — Stop/liquidation events: accelerated price movement, volume explosion, liquidity disappearance, continuation vs reversal.
Phase 42 — Volatility transmission: VIX→ES, rates vol→FX, FX vol→equities, commodity vol→currencies.
Phase 43 — Correlation breaks: historically connected assets suddenly diverging.
Phase 44 — Regime-specific edges: ask "Strategy + regime = profitable?" not just "Strategy = profitable?"
Phase 45 — Capacity: test 1/2/5/10/25/50/100... contracts until market impact destroys the edge.

PHASES 46+ — R001 ACTUAL EXPERIMENT

This is where we are right now.

R001: Asia → Europe → New York session-shadow experiment, starting with ES.

46 — Data acquisition: minimum ES 1-minute OHLCV, preferred individual contracts, eventually tick/quotes/MBO. CME's official historical infrastructure supports all levels.

47 — Data validation: before analysis, check missing bars, duplicates, bad timestamps, impossible prices, zero volume, roll errors, holiday errors, DST errors.

48 — Contract handling: maintain contract master (expiration, last trade, volume, open interest, settlement, roll date). Never blindly splice contracts.

49 — Session construction: for each trading day, build Asia/Europe/New York sessions with exchange-calendar-aware timestamps.

50 — Session geometry: for each session — open, high, low, close, VWAP, volume, range, high time, low time.

51 — H001–H012 hypotheses:
Europe vs Asia: H001 touch Asia high, H002 touch Asia low, H003 break Asia high, H004 break Asia low, H005 break high+acceptance, H006 break high+rejection, H007 break low+acceptance, H008 break low+rejection.
New York vs Europe: H009 touch Europe high, H010 touch Europe low, H011 break Europe high, H012 break Europe low.

52 — Sweep-order research: classify HIGH_FIRST, LOW_FIRST, HIGH_ONLY, LOW_ONLY, BOTH, NEITHER.

53 — Sweep→rejection: level broken → price returns inside → future movement.

54 — Sweep→acceptance: level broken → price remains outside → future movement.

55 — Timing: measure whether behavior happens 0-5/5-15/15-30/30-60/60-120/120-240 min.

56 — Volatility conditioning: split by percentile (<10th, 10-25, 25-50, 50-75, 75-90, >90).

57 — Prior-session conditioning: prior return, prior range, prior close location, overnight return.

58 — Day-of-week: Mon-Fri.

59 — Macro conditioning: normal / macro / major macro.

60 — Baselines: every result compared against unconditional, randomized, matched-volatility, matched-range.

61 — Effect size: AbsoluteLift and RelativeLift.

62 — Statistical significance: confidence intervals, bootstrap, permutation tests.

63 — Multiple-testing correction (testing many hypotheses).

64 — Historical stability: check by year, quarter, month, volatility regime.

65 — Out-of-sample: e.g. DISCOVERY 2008-2021, VALIDATION 2022-2024, LOCKED TEST 2025-2026 (exact split adjustable, principle fixed — need data the model didn't learn from).

66 — Trading simulation: entry, stop, target, holding period for surviving hypotheses.

67 — Cost model: commission, exchange fees, spread, slippage.

68 — Fill model: upgrade bar → tick → quote → order book (a candle high doesn't prove we could have bought there).

69 — Markout: for each potential fill — 1ms/5ms/10ms/50ms/100ms/500ms/1s/5s/30s/1m.

70 — Execution degradation: artificially add latency/slippage/spread and see when strategy dies.

71 — Paper trading: real-time signal → simulated order → simulated fill.

72 — Live shadow: compare historical expectation vs real-time behavior.

73 — Tiny live capital: only after all previous gates.

74 — Risk engine: position, notional, drawdown, daily loss, leverage, correlation, liquidity controls.

75 — Kill switch: auto-stop on feed failure, clock failure, position mismatch, excessive slippage, unexpected volatility, risk breach, execution anomaly.

76 — Drift detection: historical signal distribution vs current signal distribution.

77 — Model versioning: model ID, data version, training dates, features, parameters, deployment date, retirement date.

78 — Continuous adaptation (only after proven): rolling models, EWMA, Kalman, regime switching, online learning, adaptive thresholds. Never let the system blindly "learn" from live noise.

79 — Portfolio construction: combine session/cross-market/event/microstructure strategies, market making, stat arb.

80 — Portfolio-level risk: strategy correlation, factor exposure, liquidity concentration, tail risk, aggregate drawdown.

81 — Capacity: how much capital can the strategy handle before its own trading destroys the edge?

82 — Infrastructure optimization (only now): better internet, VPS, cloud, dedicated server, C++, Rust, kernel tuning, co-location, direct feeds, FPGA. Don't buy infrastructure before knowing whether the edge needs it.

83 — Broker/execution integration: eventually connect proven strategy to actual trading account. Robinhood remains useful for personal trading but is not the historical research database. For serious HFT execution research, evaluate broker/exchange connectivity, APIs, data feeds, order types, fees, latency appropriate to the strategy.

84 — Production monitoring: dashboard for P&L, positions, orders, fills, latency, slippage, drawdown, signal quality, data health, model health.

85 — Disaster recovery: internet loss, power loss, exchange outage, data corruption, software crash, bad deployment, stale feed, duplicate order.

86 — Research governance: every experiment permanently recorded. No "I changed the rule after seeing the result" without recording that it happened.

87 — Strategy retirement: strategies are ACTIVE / DEGRADED / PAUSED / RESEARCH / RETIRED. Doesn't stay alive just because it used to make money.

88 — Continuous global scanning: once the engine works, systematically scan Asia/Europe/US, FX, rates, commodities, equities, futures, options for new relationships.

89 — Machine learning (only now): logistic regression, gradient boosting, random forest, neural networks, sequence models, online learning. ML is a layer on top of clean market research, not a replacement for it.

90 — The eventual autonomous research loop:
GLOBAL MARKETS → DATA FEEDS → DATA VALIDATION → TIME/SESSION ENGINE → FEATURE ENGINE → HYPOTHESIS GENERATOR → BACKTESTER → STATISTICAL FILTER → EXECUTION SIMULATOR → ADVERSARIAL TEST → PAPER/SHADOW → LIVE TEST → RISK ENGINE → PERFORMANCE DATA → FEEDBACK/ADAPTATION → (loops back to) RESEARCH

WHAT WE HAVE

Research architecture (90-ish phases from market research through production), market structure framework (global trading is an overlapping network, not isolated exchange openings), data hierarchy (bars → trades → quotes → order book → MBO), session framework (Asia → Europe → New York → next Asia, with real exchange calendars and auctions underneath), hypothesis framework (H001-H012 defined), statistical framework (baseline, effect size, significance, multiple testing, out-of-sample, walk-forward, Monte Carlo), execution framework (fills, slippage, queue, latency, adverse selection, market impact), risk framework (position, drawdown, exposure, regime, drift, kill switch), long-term architecture (research → trading → feedback loop).

WHAT IS MISSING

1. Actual ES historical bars — immediate blocker; we have the spec, not the dataset.
2. Official exchange calendar database — need to implement, not manually guess sessions.
3. Individual ES contract history — need to properly handle ESH/ESM/ESU/ESZ etc., not blindly splice a continuous series.
4. Macro-event dataset — release timestamp, consensus, actual, prior, revision.
5. Cross-market historical data — NQ, RTY, ZN, ZB, 6E, 6J, 6B, GC, CL, DAX, EuroStoxx, Nikkei, HSI, EURUSD, USDJPY, USDCNH.
6. Tick data — needed once a bar-level pattern survives.
7. Quote/order-book data — needed to determine if we could actually get filled.
8. Live feed — needed for shadow trading.
9. Execution connection — needed only once we have something worth executing.

WHAT WE ARE BUILDING

Not simply "a trading bot" — a quantitative market research laboratory that can eventually become a trading system, with four layers:
Layer 1 — Market intelligence: what is happening?
Layer 2 — Statistical intelligence: what repeatedly happens next?
Layer 3 — Execution intelligence: can we actually capture it?
Layer 4 — Adaptive intelligence: is it still working?

THE FINAL OBJECTIVE

Eventually the system should answer questions like: "It's 8:31 AM New York time. Asia had a compressed range, London swept the Asian high and rejected it, USDJPY is doing X, ZN is doing Y, NQ/ES relationship is Z, volatility is at the 72nd percentile, and there is no major macro release for the next hour. What has historically happened in this exact market state, how often, over what horizon, and what would the expected net P&L be after realistic execution?" — answered from data, not intuition.

MARKET STATE → PROBABILITY DISTRIBUTION → EXPECTED VALUE → EXECUTION QUALITY → RISK → TRADE/DON'T TRADE

WHERE WE ARE RIGHT NOW

PHASES 1-90 → R001 SPECIFICATION → WAITING FOR ACTUAL ES DATA → VALIDATE DATA → RUN H001-H012 → FIRST REAL STATISTICAL RESULT

We have not yet proven the session-shadow strategy profitable. We have established that the market structure makes the question worth testing, and built the framework that will tell us whether the hypothesis survives.

CME describes historical data as intended for backtesting and strategy validation and provides progressively deeper datasets from trades to MBO. Nothing is missing conceptually now — the immediate missing ingredient is actual historical market data.

THE NEXT ACTION

Do not download anything yet. Choose the exact data route:

A. Free/cheap 1-minute ES data → prove R001 works
B. Paid CME historical data → start with exchange-grade data
C. Hybrid: cheap 1-minute research first, then CME tick/MBO only for surviving strategies.

Recommended route: C. It avoids spending heavily before establishing that the first statistical hypotheses deserve deeper investigation, while ultimately putting serious strategies on exchange-grade data.
