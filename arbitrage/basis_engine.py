"""
Basis Engine - Spot vs. Perpetual Futures Spread & Convergence Analyzer.
Calculates the premium/discount between Spot and Futures markets to quantify
cash-and-carry basis trade profitability.
"""
from typing import Dict, Any, List
from datetime import datetime, timezone


class BasisEngine:
    """
    Monitors the spot-to-futures price spread (Basis) to lock in risk-free convergence yield.
    """

    @staticmethod
    def calculate_basis(spot_price: float, futures_price: float, days_to_expiry: float = 365.0) -> Dict[str, Any]:
        """
        Calculates absolute basis, basis percentage, and annualized basis APR.
        Basis = Futures Price - Spot Price
        """
        if spot_price <= 0:
            return {"basis": 0.0, "basis_pct": 0.0, "annualized_basis_apr": 0.0, "regime": "PARITY"}

        basis = futures_price - spot_price
        basis_pct = (basis / spot_price) * 100.0
        
        # Annualized APR
        annualized_apr = (basis_pct * (365.0 / max(days_to_expiry, 1.0)))

        regime = "CONTANGO" if basis > 0 else ("BACKWARDATION" if basis < 0 else "PARITY")

        return {
            "spot_price": spot_price,
            "futures_price": futures_price,
            "basis": round(basis, 4),
            "basis_pct": round(basis_pct, 4),
            "annualized_basis_apr": round(annualized_apr, 2),
            "regime": regime,
            "arbitrage_recommendation": "CASH_AND_CARRY_LONG_SPOT_SHORT_FUTURES" if basis > 0 else "REVERSE_CASH_AND_CARRY"
        }
