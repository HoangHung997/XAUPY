"""Analyze every acquired timeframe CSV without changing any trading profile."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from xaupy_engine.calibration import analyze_candles


def write_report(summaries: list[dict], path: Path) -> None:
    def fmt(value: float | None) -> str:
        return "—" if value is None else f"{value:.4f}"
    total = sum(item["bars"] for item in summaries)
    passed = sum(row["status"] == "RESEARCH_CANDIDATE"
                 for item in summaries for row in item["selections"])
    lines = ["# Nghiên cứu RSI/Z trên lịch sử MT5", "",
             f"Đã phân tích {total:,} nến đóng, {len(summaries)} khung thời gian; "
             f"90 bộ tham số/khung. {passed} ứng viên vượt điều kiện kiểm tra ngoài mẫu.", "",
             "Đây là nghiên cứu phản ứng giá sau tín hiệu đảo chiều, chưa phải lợi nhuận của toàn bộ chiến lược "
             "Direction → Pullback → Trigger. Không tự áp tham số vào profile đang chạy.", "",
             "## Phương pháp", "",
             "- RSI Wilder và Z dùng độ lệch chuẩn tổng thể, khớp công thức Engine.",
             "- Ghi nhận chạm ngưỡng từ high/low trong nến; chỉ xác nhận hồi tại giá đóng của nến sau; "
             f"giá vào giả định ở open kế tiếp, giá ra ở close sau {summaries[0]['horizon_bars']} nến; setup hết hạn sau 2 nến.",
             "- Loại setup và kết quả đi qua khoảng trống thời gian, kể cả nghỉ thị trường; không tự lấp nến thiếu.",
             "- Các sự kiện không chồng thời gian. Chia 60% chọn tham số, 20% kiểm tra, 20% kiểm tra cuối; "
             "không chuyển setup hoặc kết quả vượt ranh giới mẫu.",
             "- Chọn riêng từng họ RSI, Z, RSI+Z bằng cận dưới trung bình của mẫu đầu. "
             "Hai mẫu sau không được dùng để đổi lựa chọn.",
             "- Trừ spread lịch sử theo nến. Phí và trượt giá bổ sung chỉ có khi truyền --extra-cost; "
             "không có SL/TP, quản trị vốn hoặc bộ lọc hướng trong phép đo này.",
             "- Khoảng tin cậy là mô tả thống kê; chưa hiệu chỉnh toàn bộ việc thử nhiều bộ tham số "
             "hoặc phụ thuộc theo thời gian. OHLC không chứng minh được thứ tự từng tick.", "",
             "## Dữ liệu và ứng viên được chọn trên mẫu đầu", "",
             "Các mức dưới đây là kết quả nghiên cứu, không phải bộ cấu hình đã được xác nhận để giao dịch. "
             "Đơn vị kết quả là chênh lệch giá XAUUSD sau spread, không phải USD tài khoản hoặc phần trăm lợi nhuận.", "",
             "| Khung | Nến | Họ | Tham số | Số sự kiện test | TB kiểm tra | TB test | Kết luận |",
             "|---|---:|---|---|---:|---:|---:|---|"]
    order = {tf: i for i, tf in enumerate(("M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4"))}
    for item in sorted(summaries, key=lambda x: order[Path(x["source"]).stem.split("_")[-1]]):
        timeframe = Path(item["source"]).stem.split("_")[-1]
        for row in item["selections"]:
            if "parameters" not in row:
                continue
            p = row["parameters"]
            params = []
            if row["family"] != "Z":
                params.append(f"RSI({p['rsi_period']}) {100-p['rsi_sell']:g}/{p['rsi_sell']:g}, hồi {p['rsi_delta']:g}")
            if row["family"] != "RSI":
                params.append(f"Z({p['z_period']}) ±{p['z_sell']:g}, hồi {p['z_delta']:g}")
            state = "Cần kiểm tra tick" if row["status"] == "RESEARCH_CANDIDATE" else "Chưa đạt"
            lines.append(f"| {timeframe} | {item['bars']:,} | {row['family']} | {'; '.join(params)} | "
                         f"{row['test']['events']} | {fmt(row['validation']['mean_net_price'])} | "
                         f"{fmt(row['test']['mean_net_price'])} | {state} |")
    lines += ["", "## Chạm trong nến so với chỉ nhìn giá đóng", "",
              "Cùng bộ tham số được chọn, cùng mẫu test; số sự kiện có thể tăng hoặc giảm do "
              "quy tắc không chồng sự kiện và thời điểm kích hoạt khác nhau.", "",
              "| Khung | Họ | Chạm trong nến: sự kiện / TB | Chỉ giá đóng: sự kiện / TB |",
              "|---|---|---:|---:|"]
    for item in summaries:
        tf = Path(item["source"]).stem.split("_")[-1]
        for row in item["selections"]:
            if "close_only" not in row:
                continue
            live, closed = row["test"], row["close_only"]["test"]
            closed_mean = "—" if closed["mean_net_price"] is None else f"{closed['mean_net_price']:.4f}"
            lines.append(f"| {tf} | {row['family']} | {live['events']} / {fmt(live['mean_net_price'])} | "
                         f"{closed['events']} / {closed_mean} |")
    lines += ["", "## Nguồn và khả năng tái lập", "",
              "Mỗi JSON theo khung chứa SHA-256 của CSV nguồn, mốc tách mẫu, đầy đủ 90 kết quả, "
              "các chi phí giả định và đối chiếu với cách chỉ lấy giá đóng.", "",
              "[MetaQuotes CopyRates](https://www.mql5.com/en/docs/series/copyrates) mô tả giới hạn lịch sử; "
              "[CopyTicks](https://www.mql5.com/en/docs/series/copyticks) giải thích vì sao OnTick không đại diện mọi tick. "
              "[Bailey và cộng sự](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) trình bày rủi ro chọn tham số quá khớp dữ liệu.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--point-size", type=float, required=True)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--extra-cost", type=float, default=0.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for path in sorted(args.directory.glob("XAUUSD_*.csv")):
        print(f"Analyzing {path.name}", flush=True)
        result = analyze_candles(path, point_size=args.point_size, horizon=args.horizon,
                                 extra_cost=args.extra_cost)
        (args.output / (path.stem + ".json")).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        summaries.append({k: v for k, v in result.items() if k != "candidates"})
        print(f"Finished {path.name}: {result['bars']} bars", flush=True)
    if not summaries:
        raise SystemExit("No XAUUSD_<TF>.csv files in input directory")
    (args.output / "summary.json").write_text(json.dumps({
        "created_utc": datetime.now(timezone.utc).isoformat(), "timeframes": summaries,
    }, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    write_report(summaries, args.output / "report.md")


if __name__ == "__main__":
    main()
