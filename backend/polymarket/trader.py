"""
trader.py — Ejecuta órdenes en Polymarket usando py-clob-client SDK oficial.

NO implementa EIP-712 signing manual. Usa ClobClient del SDK.

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

Funciones:
    place_market_order(token_id, side, amount_usdc) → str | None  (order_id)
    get_position(market_id)                         → dict

En DRY_RUN=true: loguea la orden sin ejecutar, retorna "DRY_RUN_ORDER".
Maneja: fondos insuficientes, mercado cerrado, slippage excesivo.
"""
