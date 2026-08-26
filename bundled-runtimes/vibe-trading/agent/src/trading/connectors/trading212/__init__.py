"""Trading 212 broker connector.

Read-only account, portfolio, order, order-history, and instrument-metadata
access through Trading 212's public REST API. The public API does not expose a
runtime paper/live discriminator that this connector can verify, so order
placement and cancellation are intentionally disabled.
"""
