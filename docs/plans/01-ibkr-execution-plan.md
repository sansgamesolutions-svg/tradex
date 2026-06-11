# IBKR Execution Plan

**Status:** Implemented

## Objective

Add an Interactive Brokers execution adapter for stock and forex orders while
keeping order creation independent from broker-specific APIs.

## Delivered Work

1. Implement an IBKR adapter in `tradex/execution/ibkr.py`.
2. Support market and limit orders through TWS or IB Gateway.
3. Normalize stock and forex instruments into IBKR contracts.
4. Return common order result objects instead of exposing broker responses.
5. Make preview mode the default so orders are not transmitted accidentally.
6. Add CLI routing and centralized connection settings.

## Interfaces

- Platform name: `ibkr`
- Supported assets: stocks and forex
- Supported order types: market and limit
- Required configuration: host, port, client ID, and account where applicable
- Common request fields: symbol, side, quantity, order type, and limit price

## Safety Requirements

- Do not transmit an order unless live execution is explicitly requested.
- Validate positive quantities and require a price for limit orders.
- Keep credentials and account identifiers out of logs and object
  representations.
- Surface connection and broker rejection errors without silently retrying an
  order submission.

## Validation

- Test stock and forex contract construction.
- Test market and limit order conversion.
- Test preview and live execution paths separately.
- Test invalid quantities, missing limit prices, and broker failures.
- Confirm the adapter satisfies the shared trading platform contract.

## Extension Boundary

Advanced IBKR order types, options, futures, bracket orders, and broker-side
portfolio management remain separate follow-up work. They can be added without
changing the common order request contract.
