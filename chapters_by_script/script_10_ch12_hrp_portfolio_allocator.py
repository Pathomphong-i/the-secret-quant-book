import numpy as np
import pandas as pd
from typing import Dict, List, Optional


class AdaptivePortfolioAllocator:
    """
    สมองกลจัดสรรน้ำหนักพอร์ตที่ถูกต้องและใช้งานได้จริง (AI Portfolio Allocator)
    รองรับ:
      1. Inverse-Volatility Weighting
      2. Hierarchical Risk Parity (HRP - López de Prado) แบบครบวงจร
      3. Conviction-Tilted Risk Allocation + Regime-Aware Cash Buffer
      4. Portfolio Volatility Targeting & Position Concentration Caps
    """

    def __init__(
        self,
        cov_window: int = 60,
        target_portfolio_vol: float = 0.16,  # เป้าหมายความผันผวนพอร์ต 16% ต่อปี
        max_single_weight: float = 0.25,     # ห้ามถือหุ้นตัวเดียวเกิน 25% ของพอร์ต
        min_position_weight: float = 0.03,   # ถ้าน้ำหนักต่ำกว่า 3% ให้ปัดทิ้งเพื่อประหยัดค่าคอมฯ
    ):
        self.cov_window = cov_window
        self.target_portfolio_vol = target_portfolio_vol
        self.max_single_weight = max_single_weight
        self.min_position_weight = min_position_weight

    # ------------------------------------------------------------------
    # 1. Inverse-Volatility Weighting
    # ------------------------------------------------------------------
    @staticmethod
    def compute_inverse_vol_weights(returns_df: pd.DataFrame) -> pd.Series:
        """คำนวณน้ำหนักผกผันกับความผันผวนรายตัว"""
        vols = returns_df.std() * np.sqrt(252)
        vols = vols.replace(0, np.nan).fillna(vols.median() if len(vols) > 0 else 1.0)
        inv_vol = 1.0 / vols
        return inv_vol / inv_vol.sum()

    # ------------------------------------------------------------------
    # 2. Hierarchical Risk Parity (HRP) - Full Implementation
    # ------------------------------------------------------------------
    @staticmethod
    def _cluster_variance(cov: pd.DataFrame, items: List[str]) -> float:
        """คำนวณความแปรปรวนของกลุ่มย่อย (Cluster Variance) ด้วยน้ำหนัก Inverse-Variance ภายในกลุ่ม"""
        sub_cov = cov.loc[items, items]
        diag_var = np.diag(sub_cov.values)
        inv_diag = 1.0 / np.where(diag_var > 1e-12, diag_var, 1e-12)
        w = inv_diag / np.sum(inv_diag)
        return float(w.T @ sub_cov.values @ w)

    @staticmethod
    def _quasi_diagonal_order(dist_matrix: np.ndarray) -> List[int]:
        """
        จัดเรียงลำดับดัชนีสินทรัพย์ด้วย Single-Linkage Hierarchical Clustering Tree
        เพื่อให้สินทรัพย์ที่มีความสัมพันธ์ใกล้ชิดกันเรียงอยู่ติดกันบนแกนเมทริกซ์
        """
        n = dist_matrix.shape[0]
        if n <= 1:
            return list(range(n))

        # เริ่มต้นให้แต่ละสินทรัพย์เป็นคลัสเตอร์เดี่ยวของตัวเอง
        clusters: List[List[int]] = [[i] for i in range(n)]
        dist = dist_matrix.copy().astype(float)
        np.fill_diagonal(dist, np.inf)

        # รวมคลัสเตอร์ที่อยู่ใกล้กันที่สุดทีละคู่จนเหลือต้นไม้เดียว
        while len(clusters) > 1:
            min_d = np.inf
            merge_pair = (0, 1)
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    # Single-linkage distance ระหว่างคลัสเตอร์ i และ j
                    d_ij = min(dist[a, b] for a in clusters[i] for b in clusters[j])
                    if d_ij < min_d:
                        min_d = d_ij
                        merge_pair = (i, j)

            idx_a, idx_b = merge_pair
            clusters[idx_a] = clusters[idx_a] + clusters[idx_b]
            clusters.pop(idx_b)

        return clusters[0]

    def compute_hrp_weights(self, returns_df: pd.DataFrame) -> pd.Series:
        """
        คำนวณน้ำหนักพอร์ตด้วย Hierarchical Risk Parity (HRP):
        ขั้นที่ 1: คำนวณ Correlation Distance Matrix
        ขั้นที่ 2: จัดเรียงลำดับสินทรัพย์ (Quasi-Diagonalization)
        ขั้นที่ 3: แบ่งครึ่งงบความเสี่ยงซ้ำๆ จากบนลงล่าง (Recursive Bisection)
        """
        cols = list(returns_df.columns)
        if len(cols) == 0:
            return pd.Series(dtype=float)
        if len(cols) == 1:
            return pd.Series({cols[0]: 1.0})

        cov = returns_df.cov() * 252.0
        corr = returns_df.corr().fillna(0.0).clip(-1.0, 1.0)

        # ขั้นที่ 1: แปลงสหสัมพันธ์เป็นระยะห่างทางเรขาคณิต d_ij = sqrt(0.5 * (1 - corr_ij))
        dist_corr = np.sqrt(np.clip(0.5 * (1.0 - corr.values), 0.0, 1.0))
        # วัดระยะห่างยุคลิดระหว่างคอลัมน์ของเมทริกซ์ระยะห่างอีกชั้นเพื่อความเสถียร
        n = len(cols)
        euclidean_dist = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d = np.linalg.norm(dist_corr[:, i] - dist_corr[:, j])
                euclidean_dist[i, j] = d
                euclidean_dist[j, i] = d

        # ขั้นที่ 2: Quasi-Diagonalization
        ordered_indices = self._quasi_diagonal_order(euclidean_dist)
        sorted_items = [cols[idx] for idx in ordered_indices]

        # ขั้นที่ 3: Recursive Bisection
        weights = pd.Series(1.0, index=sorted_items, dtype=float)
        clustered_items: List[List[str]] = [sorted_items]

        while len(clustered_items) > 0:
            # แยกคลัสเตอร์ที่มีสมาชิกมากกว่า 1 ตัวออกเป็นซ้ายและขวาอย่างละครึ่ง
            next_clusters: List[List[str]] = []
            for cluster in clustered_items:
                if len(cluster) > 1:
                    mid = len(cluster) // 2
                    next_clusters.append(cluster[:mid])
                    next_clusters.append(cluster[mid:])
            clustered_items = next_clusters

            # จัดสรรน้ำหนักระหว่างคู่กิ่งซ้ายและกิ่งขวาตามสัดส่วนผกผันความแปรปรวน
            for i in range(0, len(clustered_items), 2):
                left_items = clustered_items[i]
                right_items = clustered_items[i + 1]

                var_left = self._cluster_variance(cov, left_items)
                var_right = self._cluster_variance(cov, right_items)

                alpha = 1.0 - (var_left / max(var_left + var_right, 1e-12))
                weights[left_items] *= alpha
                weights[right_items] *= (1.0 - alpha)

        return weights.reindex(cols) / weights.sum()

    # ------------------------------------------------------------------
    # 3. การรวมร่าง: HRP + AI Conviction + Regime Cash Buffer
    # ------------------------------------------------------------------
    def allocate_portfolio(
        self,
        price_history_df: pd.DataFrame,
        ai_convictions: Dict[str, float],
        regime_probs: Dict[str, float],
        method: str = "HRP",
    ) -> Dict[str, float]:
        """
        คำนวณสัดส่วนเงินลงทุนสุทธิของแต่ละหุ้นและสัดส่วนเงินสดสำรอง (CASH)
        - price_history_df: ตารางราคาปิดย้อนหลัง (คอลัมน์ = ชื่อหุ้น)
        - ai_convictions: คะแนนความมั่นใจจากสภาบอทของแต่ละหุ้น (คัดเฉพาะตัวที่เป็นบวก)
        - regime_probs: ความน่าจะเป็นของสภาวะตลาดปัจจุบัน
        """
        # คัดเฉพาะหุ้นที่มีคะแนนความมั่นใจเป็นบวก
        active_symbols = [
            sym for sym, score in ai_convictions.items()
            if score > 0.05 and sym in price_history_df.columns
        ]

        if not active_symbols:
            return {"CASH": 1.0}

        recent_prices = price_history_df[active_symbols].tail(self.cov_window + 1)
        returns_df = recent_prices.pct_change().dropna(how="all").fillna(0.0)

        # 1. คำนวณน้ำหนักฐานด้านความเสี่ยง (Risk-Based Base Weights)
        if method.upper() == "HRP" and len(active_symbols) >= 2:
            base_weights = self.compute_hrp_weights(returns_df)
        else:
            base_weights = self.compute_inverse_vol_weights(returns_df)

        # 2. ถ่วงน้ำหนักผสมกับความมั่นใจของสภา AI (Conviction Tilt)
        conviction_series = pd.Series({s: ai_convictions[s] for s in active_symbols})
        tilted_weights = base_weights * conviction_series
        if tilted_weights.sum() <= 0:
            return {"CASH": 1.0}
        tilted_weights /= tilted_weights.sum()

        # 3. คำนวณสัดส่วนการถือหุ้นรวมสูงสุดตามสภาวะตลาด และความผันผวนของพอร์ต
        p_crisis = float(regime_probs.get("HIGH_VOL_CRISIS", 0.0))
        p_sideways = float(regime_probs.get("SIDEWAYS", 0.0))

        # ลดเพดานการถือหุ้นรวมเมื่อตลาดมีความเสี่ยงวิกฤตหรือไซด์เวย์หนัก
        regime_exposure_cap = np.clip(1.0 - (1.20 * p_crisis) - (0.25 * p_sideways), 0.0, 1.0)

        # คำนวณความผันผวนคาดการณ์ของพอร์ตรวม (Ex-Ante Portfolio Volatility)
        cov_matrix = returns_df.cov().values * 252.0
        w_vec = tilted_weights.values
        realized_port_vol = float(np.sqrt(max(w_vec.T @ cov_matrix @ w_vec, 1e-8)))

        # Volatility Scaling Factor: ถ้าพอร์ตเหวี่ยงแรงกว่าเป้าหมาย ให้ลดหน้าตักรวมลงอัตโนมัติ
        vol_scaling_factor = min(1.0, self.target_portfolio_vol / realized_port_vol)
        total_equity_exposure = float(regime_exposure_cap * vol_scaling_factor)

        # 4. คูณสัดส่วนหุ้นรายตัวและบังคับเพดานสูงสุดต่อตัว (Concentration Cap)
        final_weights = (tilted_weights * total_equity_exposure).clip(upper=self.max_single_weight)

        # ตัดหุ้นที่ได้น้ำหนักน้อยเกินไปออกเพื่อไม่ให้เสียค่าคอมมิชชั่นจุกจิก
        final_weights = final_weights[final_weights >= self.min_position_weight]

        allocation: Dict[str, float] = {
            sym: round(float(w), 4) for sym, w in final_weights.items()
        }
        invested_sum = sum(allocation.values())
        allocation["CASH"] = round(max(0.0, 1.0 - invested_sum), 4)

        return allocation


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2024-01-01", periods=100)
    prices_df = pd.DataFrame({
        "STOCK_UTIL": 30.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.008, 100))),
        "STOCK_ICT": 200.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.010, 100))),
        "STOCK_FIN_1": 45.0 * np.exp(np.cumsum(rng.normal(0.0006, 0.022, 100))),
        "STOCK_FIN_2": 40.0 * np.exp(np.cumsum(rng.normal(0.0006, 0.022, 100))),
    }, index=dates)
    allocator = AdaptivePortfolioAllocator()
    weights = allocator.allocate_portfolio(
        price_history_df=prices_df,
        ai_convictions={"STOCK_UTIL": 0.75, "STOCK_ICT": 0.80, "STOCK_FIN_1": 0.65, "STOCK_FIN_2": 0.65},
        regime_probs={"BULL_TREND": 0.70, "SIDEWAYS": 0.20, "HIGH_VOL_CRISIS": 0.10},
        method="HRP",
    )
    print("=== สัดส่วนการจัดพอร์ตด้วย Hierarchical Risk Parity (HRP) ===")
    for k, v in weights.items():
        print(f"  - {k:<12}: {v * 100.0:>5.2f}%")
