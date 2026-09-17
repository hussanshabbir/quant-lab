# quant lab

A solo systematic-trading research lab built from scratch in
 Python. It ingests and validates raw futures market data (C
ME ES via Databento, with automated bad-tick and contract-ro
ll detection), builds a timezone- and exchange-calendar-awar
e session engine, and runs pre-registered statistical hypoth
esis tests — covering session breakouts, cross-market lead-l
ag, volatility-regime persistence, and options premium strat
egies — through a discovery/validation/locked-test split wit
h permutation testing and multiple-testing correction. A cos
t-aware trading simulation layer then stress-tests any stati
stically significant pattern against realistic commissions,
slippage, and fills before it's considered a real edge, and
every experiment (including killed and negative results) is
permanently logged for full research-governance auditability.
