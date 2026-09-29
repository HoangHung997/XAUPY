using XAUPY.Ipc;

namespace XAUPY.Desktop;

/// <summary>User-facing reasons; raw codes remain in diagnostics and the journal.</summary>
public static class ExecutionPresentation
{
    public static string Reason(string? code)
    {
        string message = code switch
        {
            null or "" => "Sẵn sàng",
            "USER_STOPPED" => "Đã dừng giao dịch; chọn Thủ công hoặc Tự động để bắt đầu.",
            "USER_CONFIRMATION_REQUIRED" => "Tích Xác nhận đặt lệnh ở ngay trên nút BUY/SELL.",
            "ENGINE_OFFLINE" => "Mất kết nối Python Engine.",
            "MARKET_DATA_STALE" or "TERMINAL_DISCONNECTED" => "Chưa có dữ liệu tài khoản MT5 mới; đang chờ kết nối lại.",
            "FRESH_QUOTE_REQUIRED" => "Giá chưa đủ mới hoặc đồng hồ giá không khớp. Chờ tick mới; không gửi lại liên tục.",
            "BROKER_CLOCK_REQUIRED" => "Thiếu thời gian server MT5; cần kiểm tra EA Bridge.",
            "BRIDGE_UPGRADE_REQUIRED" => "EA trên MT5 chưa hỗ trợ thực thi. Dùng EA đi kèm đúng bản app.",
            "ACCOUNT_IDENTITY_REQUIRED" => "Chưa đọc được danh tính tài khoản từ MT5.",
            "USER_REAL_PERMISSION_REQUIRED" => "Quyền REAL trong Cài đặt và profile chưa cùng được cho phép.",
            "ACCOUNT_OR_SYMBOL_CHANGED" or "CONFIRMED_ACCOUNT_MISMATCH" => "Tài khoản hoặc symbol đã đổi; chọn lại chế độ và xác nhận danh tính mới.",
            "PROFILE_BRIDGE_IDENTITY_MISMATCH" => "Symbol/Magic của profile không khớp EA đang kết nối.",
            "RECONCILIATION_REQUIRED" => "Có lệnh đang chờ đối chiếu broker. Xem Tiến trình lệnh; không gửi lại.",
            "AWAITING_POST_TRADE_SNAPSHOT" => "Đang chờ MT5 cập nhật vị thế sau thao tác vừa gửi.",
            "STARTUP_BRIDGE_SYNC_PENDING" => "Đang đồng bộ tài khoản và lịch sử trước khôi phục giao dịch.",
            "EXECUTION_STORAGE_UNAVAILABLE" => "Không đọc/ghi được sổ thực thi; giao dịch bị chặn để tránh gửi trùng.",
            "LEGACY_DEMO_ATTEMPT_UNRESOLVED" => "Lần DEMO một lệnh trước đó chưa đối chiếu xong.",
            "SESSION_BLOCKED" => "Ngoài ngày/giờ giao dịch đã chọn trong Cấu hình.",
            "WEEKEND_CLOSE_WINDOW" => "Đang trong khoảng đóng lệnh trước cuối tuần.",
            "MAX_OPEN_POSITIONS" => "Đã đạt giới hạn vị thế/lệnh chờ, kể cả yêu cầu đang xếp hàng.",
            "MAX_TRADES_PER_DAY" => "Đã đạt số lệnh tối đa trong ngày.",
            "MAX_CONSECUTIVE_LOSSES" => "Đã đạt giới hạn số lệnh thua liên tiếp.",
            "DAILY_LOSS_LIMIT" or "DAILY_RISK_ALREADY_COMMITTED" => "Đã chạm ngân sách rủi ro ngày; chỉ quản lý hoặc giảm vị thế hiện có.",
            "DAILY_TARGET_REACHED" => "Đã đạt mục tiêu ngày theo cấu hình.",
            "COOLDOWN" => "Đang chờ hết thời gian nghỉ sau lệnh trước.",
            "BROKER_HISTORY_INCOMPLETE" or "BROKER_DAY_HISTORY_REQUIRED" => "Lịch sử broker của ngày hiện tại chưa đồng bộ đủ.",
            "NEWS_WINDOW" => "Trong khoảng tránh tin tức đã cấu hình.",
            "NEWS_CALENDAR_UNAVAILABLE" => "Chưa có lịch tin đủ mới để kiểm điều kiện vào lệnh.",
            "SPREAD_LIMIT" or "MAX_SPREAD" or "SPREAD_TOO_HIGH" => "Spread vượt giới hạn trong Cấu hình.",
            "RISK_BUDGET_EXCEEDED" => "Lot và SL vượt ngân sách rủi ro; giảm lot hoặc kiểm cấu hình rủi ro.",
            "REQUESTED_VOLUME_NOT_ALLOWED" => "Lot vượt giới hạn hoặc không khớp bước lot của broker.",
            "VOLUME_BELOW_BROKER_MINIMUM" => "Khối lượng sau chuẩn hóa nhỏ hơn lot tối thiểu của broker.",
            "PARTIAL_REMAINDER_BELOW_MINIMUM" => "Đóng một phần sẽ để lại khối lượng nhỏ hơn lot tối thiểu.",
            "NO_TARGETS" => "Không có vị thế hoặc lệnh chờ phù hợp để thực hiện.",
            "NEVER_WIDEN_SL" => "Không được nới SL hoặc tăng khoảng rủi ro của lệnh chờ.",
            "STOP_OR_FREEZE_LEVEL" or "PENDING_PRICE_TOO_CLOSE" => "Giá/SL quá gần mức hiện tại theo Stops/Freeze của broker.",
            "STOP_CONFIRM_SIGNAL_BAR_REQUIRED" or "STOP_HISTORY_WARMUP" or "STOP_HISTORY_STALE" => "Chưa có nến tín hiệu/lịch sử mới để tính điểm vào hoặc SL.",
            "INVALID_SERVER_STOPS" or "INVALID_SERVER_TP" => "SL/TP không hợp lệ theo giá và khoảng cách tối thiểu của broker.",
            "EXPLICIT_SL_OUTSIDE_LIMITS" => "SL nhập tay nằm ngoài khoảng SL tối thiểu/tối đa của profile.",
            "MIN_NET_RR" => "Lợi nhuận/rủi ro sau chi phí thấp hơn mức tối thiểu đã chọn.",
            "COMMISSION_LIMIT" => "Phí giao dịch vượt giới hạn trong Cấu hình.",
            "CONFIRMED_PROFILE_CHANGED" => "Cấu hình đã đổi sau khi xác nhận; kiểm lại lot/SL/TP rồi xác nhận lại.",
            "PENDING_RISK_INCREASE" => "Đổi giá lệnh chờ làm tăng khoảng rủi ro; cần thu hẹp SL tương ứng.",
            "POSITION_VOLUME_CHANGED" => "Khối lượng vị thế đã tăng sau khi xác nhận; kiểm tra rồi xác nhận lại.",
            "RESTORE_CONFIRMATION_REQUIRED" => "Khôi phục cần xem trước và xác nhận thay đổi; không tự bật giao dịch.",
            "RESTORE_PREVIEW_CHANGED" => "Cấu hình, tài khoản hoặc bản sao lưu đã đổi. Xem trước và xác nhận lại.",
            "BROKER_CAPABILITIES_INVALID" => "EA chưa cung cấp đủ thông số quyền và chế độ broker. Cập nhật EA đi kèm app.",
            "BROKER_SERVER_SL_UNSUPPORTED" => "Symbol không hỗ trợ SL trên server; không được mở lệnh thiếu bảo vệ.",
            "BROKER_SERVER_TP_UNSUPPORTED" => "Symbol không hỗ trợ TP trên server theo cấu hình đã chọn.",
            "BROKER_MARKET_ORDERS_UNSUPPORTED" => "Symbol không hỗ trợ lệnh thị trường.",
            "BROKER_STOP_ORDERS_UNSUPPORTED" => "Symbol không hỗ trợ lệnh Stop.",
            "BROKER_LIMIT_ORDERS_UNSUPPORTED" => "Symbol không hỗ trợ lệnh Limit.",
            "BROKER_EXPIRATION_NOT_SUPPORTED" => "Broker không hỗ trợ thời hạn lệnh chờ đã chọn; không tự đổi thành lệnh vô thời hạn.",
            "NETTING_SYMBOL_ALREADY_EXPOSED" => "Tài khoản netting đã có vị thế trên symbol này; không gộp thêm vị thế của chiến lược.",
            "TRADE_PERMISSION_DISABLED" => "MT5, EA hoặc tài khoản chưa cho phép giao dịch thuật toán. Kiểm tra quyền Algo Trading.",
            "SYMBOL_ENTRY_DISABLED" => "Broker không cho phép mở chiều giao dịch này trên symbol hiện tại.",
            "SIDE_DISABLED" => "Chiều BUY/SELL này đang tắt trong Cấu hình.",
            "CONFIRMED" or "BROKER_STATE_VERIFIED" => "Broker đã xác nhận kết quả.",
            "BROKER_PARTIAL_FILL_VERIFIED" => "Broker đã xác nhận khớp một phần khối lượng.",
            "QUEUED_FOR_BROKER" or "QUEUED" => "Đã xếp hàng, chưa có xác nhận khớp từ broker.",
            "DISPATCHED" or "UNKNOWN" or "AWAITING_BROKER" => "Đã gửi yêu cầu, đang đối chiếu broker; không bấm gửi lại.",
            "BATCH_QUEUED" => "Các thao tác đã xếp hàng; xem từng kết quả trong Tiến trình lệnh.",
            "BATCH_PARTIAL" => "Chỉ một số thao tác thành công; xem từng kết quả trong Tiến trình lệnh.",
            "APPLIED_LOCAL" or "TRAILING_ENABLED" => "Đã bật theo dõi trailing; SL chỉ đổi khi điều kiện thực tế cho phép.",
            "CANCELLED" => "Yêu cầu đã hủy trước khi gửi broker.",
            "EXPIRED" => "Yêu cầu đã quá hạn và không được gửi lại.",
            "REJECTED" => "Yêu cầu bị từ chối. Xem chi tiết trong Tiến trình lệnh hoặc Nhật ký.",
            _ => code ?? ""
        };
        return LocalizationService.T(message);
    }

    public static string Mode(ExecutionSnapshot state) => LocalizationService.T(state.Label);
    public static string Summary(ExecutionSnapshot state) =>
        !state.Fresh ? Reason("ENGINE_OFFLINE") : state.Mode == "OFF" ? Reason("USER_STOPPED") :
        $"{Mode(state)} · {Reason(state.EntryReason)}";

    public static string Permission(ExecutionSnapshot state) => LocalizationService.T(!state.PermissionsKnown ? "Quyền REAL: chưa có dữ liệu"
        : !state.LocalAllowReal ? "Quyền REAL: chưa cho phép"
        : !state.EffectiveAllowReal ? "Quyền REAL: đã lưu; profile vẫn giới hạn DEMO"
        : "Quyền REAL: đã cho phép • không tự bật giao dịch");
}
