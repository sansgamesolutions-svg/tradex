# Kraken Execution Plan

**Status:** Implemented

## Objective

Add a Kraken-backed crypto buy/sell interface that uses the same order workflow
as other TradeX execution platforms.

## Delivered Work

1. Implement the Kraken adapter in `tradex/execution/kraken.py`.
2. Connect through CCXT using API key and secret credentials.
3. Normalize user symbols into Kraken-compatible trading pairs.
4. Apply exchange amount and price precision before submission.
5. Support market and limit buy/sell orders.
6. Return common order results and retain preview-first behavior.

## Interfaces

- Platform name: `kraken`
- Supported asset: crypto
- Supported order types: market and limit
- Symbol examples: `BTC/USD`, `ETH/USD`
- Required live credentials: Kraken API key and secret

## Safety Requirements

- Preview orders unless live execution is explicitly enabled.
- Never require or expose withdrawal permissions.
- Validate that the requested market exists and is active.
- Reject invalid quantities and limit orders without a price.
- Redact credentials from errors, logs, configuration output, and `repr`.

## Validation

- Test symbol normalization and market lookup.
- Test amount and price precision handling.
- Test market and limit order payloads.
- Test missing credentials and exchange rejection behavior.
- Confirm crypto orders route to Kraken through the platform registry.

## Extension Boundary

Additional exchanges should be implemented as new platform adapters. Kraken
staking, deposits, withdrawals, margin, and derivatives are outside this
execution plan.
