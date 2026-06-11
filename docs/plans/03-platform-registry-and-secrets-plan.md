# Platform Registry and Secrets Plan

**Status:** Implemented

## Objective

Commonalize trading platform behavior so TradeX can add brokers and exchanges
without duplicating CLI logic, order validation, or secret handling.

## Delivered Work

1. Define common order request, preview, and result types.
2. Define a shared trading platform protocol in `tradex/execution/base.py`.
3. Add a registry that resolves explicit platforms and asset-class defaults.
4. Register IBKR for stock and forex execution.
5. Register Kraken for crypto execution.
6. Centralize credential loading in `tradex/config/secrets.py`.
7. Support environment variables, `_FILE` variables, and local `.env` files.
8. Redact secret values from credential object representations.

## Platform Contract

Each platform adapter is responsible for:

- Declaring its platform name and supported asset classes.
- Validating and normalizing platform-specific symbols.
- Converting the common order request into a native order.
- Producing a preview without transmitting the order.
- Returning a common result after live submission.

The CLI and calling code are responsible for:

- Building the common order request.
- Selecting a platform explicitly or through default asset routing.
- Requiring explicit confirmation for live execution.
- Displaying common previews and results.

## Secret Resolution

Resolve each secret in this order:

1. Direct environment variable.
2. Matching `_FILE` environment variable.
3. Local `.env` value.
4. Missing-secret error when the operation requires authentication.

Secret files and `.env` files must remain outside version control. Example
configuration may contain variable names and placeholders, but never real
credentials.

## Validation

- Test registry registration, lookup, duplicate handling, and default routing.
- Test adapter compatibility with the shared protocol.
- Test every secret source and its precedence.
- Test whitespace trimming and missing secret files.
- Test credential redaction.
- Confirm preview operations do not require live credential access when the
  platform can construct a preview locally.

## Extension Boundary

A new platform should require one adapter, registration metadata, configuration
keys, and adapter tests. It should not require changes to the common CLI order
flow unless it introduces a genuinely new order capability.
