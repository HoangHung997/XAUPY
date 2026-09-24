from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import math
import re
from typing import Any, Callable

PROFILE_SCHEMA_VERSION = 1
TIMEFRAME_OPTIONS = ("M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4")
MA_TYPES = ("SMA", "EMA", "SMMA", "LWMA")
PRICE_SOURCES = ("CLOSE", "OPEN", "HIGH", "LOW", "MEDIAN", "TYPICAL", "WEIGHTED")
LOGIC_OPTIONS = ("AND", "OR")
ENTRY_MODES = ("MARKET", "STOP_CONFIRM")
SL_MODES = ("FIXED", "ATR", "STRUCTURE")
TP_MODES = ("FIXED", "RR", "ZRSI_DYNAMIC")
SIZING_MODES = ("RISK_PERCENT", "FIXED_LOT")
TRAILING_MODES = ("ATR", "STRUCTURE")
SL_TIGHTEN_MODES = ("OFF", "STRUCTURE", "ATR", "ZRSI_ASSIST")
OPEN_REFERENCE_MODES = ("NONE", "DAILY_OPEN", "SESSION_OPEN", "PREVIOUS_DAY_OPEN")
EXTEND_LOGIC_OPTIONS = ("BOTH", "EITHER")

_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


@dataclass(frozen=True)
class ConfigField:
    path: str
    kind: str
    default: Any
    set_key: str
    aliases: tuple[str, ...] = ()
    enum: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""
    locked_value: Any | None = None

    def public(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "default": self.default,
            "set_key": self.set_key,
            "aliases": list(self.aliases),
            "enum": list(self.enum),
            "minimum": self.minimum,
            "maximum": self.maximum,
            "description": self.description,
            "locked_value": self.locked_value,
        }


def _f(
    path: str,
    kind: str,
    default: Any,
    set_key: str,
    *,
    aliases: tuple[str, ...] = (),
    enum: tuple[str, ...] = (),
    minimum: float | None = None,
    maximum: float | None = None,
    description: str = "",
    locked_value: Any | None = None,
) -> ConfigField:
    return ConfigField(
        path=path,
        kind=kind,
        default=default,
        set_key=set_key,
        aliases=aliases,
        enum=enum,
        minimum=minimum,
        maximum=maximum,
        description=description,
        locked_value=locked_value,
    )


FIELDS: tuple[ConfigField, ...] = (
    _f("profile.name","str","Baseline M30-M5-M1","XAUPY_ProfileName",description="Tên profile"),
    _f("profile.notes","str","","XAUPY_ProfileNotes",description="Ghi chú profile"),
    _f("strategy.symbol","str","XAUUSD","XAUPY_Symbol",aliases=("Symbol","InpSymbol")),
    _f("strategy.allow_buy","bool",True,"XAUPY_AllowBuy",aliases=("AllowBuy","InpAllowBuy")),
    _f("strategy.allow_sell","bool",True,"XAUPY_AllowSell",aliases=("AllowSell","InpAllowSell")),
    _f("timeframes.direction","enum","M30","XAUPY_DirectionTF",aliases=("DirectionTF","InpDirectionTF"),enum=TIMEFRAME_OPTIONS),
    _f("timeframes.pullback","enum","M5","XAUPY_PullbackTF",aliases=("PullbackTF","InpPullbackTF"),enum=TIMEFRAME_OPTIONS),
    _f("timeframes.trigger","enum","M1","XAUPY_TriggerTF",aliases=("TriggerTF","InpTriggerTF"),enum=TIMEFRAME_OPTIONS),

    _f("direction.ma_enabled","bool",True,"XAUPY_DirectionMAEnabled",aliases=("DirectionMAEnabled","InpDirectionMAEnabled")),
    _f("direction.ma_type","enum","EMA","XAUPY_DirectionMAType",aliases=("DirectionMAType","InpDirectionMAType"),enum=MA_TYPES),
    _f("direction.ma_period","int",50,"XAUPY_DirectionMAPeriod",aliases=("DirectionMAPeriod","InpDirectionMAPeriod"),minimum=1,maximum=1000),
    _f("direction.price_source","enum","CLOSE","XAUPY_DirectionPriceSource",aliases=("DirectionPriceSource","InpDirectionPriceSource"),enum=PRICE_SOURCES),
    _f("direction.require_close_side","bool",True,"XAUPY_DirectionRequireCloseSide",aliases=("DirectionRequireCloseSide",)),
    _f("direction.open_filter_enabled","bool",False,"XAUPY_DirectionOpenFilterEnabled",aliases=("DirectionOpenFilterEnabled","InpDirectionOpenFilterEnabled")),
    _f("direction.open_reference_mode","enum","DAILY_OPEN","XAUPY_DirectionOpenReference",aliases=("DirectionOpenReferenceMode","InpDirectionOpenReferenceMode"),enum=OPEN_REFERENCE_MODES),

    _f("pullback.logic","enum","AND","XAUPY_PullbackLogic",aliases=("PullbackLogic","InpPullbackLogic"),enum=LOGIC_OPTIONS),
    _f("pullback.rsi_enabled","bool",True,"XAUPY_PullbackRSIEnabled",aliases=("PullbackUseRSI","InpPullbackUseRSI")),
    _f("pullback.rsi_period","int",14,"XAUPY_PullbackRSIPeriod",aliases=("PullbackRSIPeriod","InpPullbackRSIPeriod"),minimum=2,maximum=200),
    _f("pullback.rsi_buy_level","float",40.0,"XAUPY_PullbackRSIBuy",aliases=("PullbackRSIBuy","InpPullbackRSIBuy"),minimum=0,maximum=100),
    _f("pullback.rsi_sell_level","float",60.0,"XAUPY_PullbackRSISell",aliases=("PullbackRSISell","InpPullbackRSISell"),minimum=0,maximum=100),
    _f("pullback.z_enabled","bool",False,"XAUPY_PullbackZEnabled",aliases=("PullbackUseZ","InpPullbackUseZ")),
    _f("pullback.z_period","int",20,"XAUPY_PullbackZPeriod",aliases=("PullbackZPeriod","InpPullbackZPeriod"),minimum=2,maximum=500),
    _f("pullback.z_buy_level","float",-2.0,"XAUPY_PullbackZBuy",aliases=("PullbackZBuy","InpPullbackZBuy"),minimum=-10,maximum=10),
    _f("pullback.z_sell_level","float",2.0,"XAUPY_PullbackZSell",aliases=("PullbackZSell","InpPullbackZSell"),minimum=-10,maximum=10),

    _f("trigger.logic","enum","AND","XAUPY_TriggerLogic",aliases=("TriggerLogic","InpTriggerLogic"),enum=LOGIC_OPTIONS),
    _f("trigger.rsi_enabled","bool",True,"XAUPY_TriggerRSIEnabled",aliases=("TriggerUseRSI","InpTriggerUseRSI")),
    _f("trigger.rsi_period","int",14,"XAUPY_TriggerRSIPeriod",aliases=("TriggerRSIPeriod","InpTriggerRSIPeriod"),minimum=2,maximum=200),
    _f("trigger.rsi_reversal_delta","float",3.0,"XAUPY_TriggerRSIDelta",aliases=("TriggerRSIDelta","InpTriggerRSIDelta"),minimum=0,maximum=50),
    _f("trigger.z_enabled","bool",False,"XAUPY_TriggerZEnabled",aliases=("TriggerUseZ","InpTriggerUseZ")),
    _f("trigger.z_period","int",20,"XAUPY_TriggerZPeriod",aliases=("TriggerZPeriod","InpTriggerZPeriod"),minimum=2,maximum=500),
    _f("trigger.z_reversal_delta","float",0.5,"XAUPY_TriggerZDelta",aliases=("TriggerZDelta","InpTriggerZDelta"),minimum=0,maximum=10),
    _f("trigger.confirm_closed_bar","bool",True,"XAUPY_TriggerClosedBar",aliases=("TriggerClosedBar","InpTriggerClosedBar")),

    _f("filters.adx.enabled","bool",False,"XAUPY_ADXEnabled",aliases=("ADXEnabled","InpADXEnabled")),
    _f("filters.adx.timeframe","enum","M5","XAUPY_ADXTF",aliases=("ADXTF","InpADXTF"),enum=TIMEFRAME_OPTIONS),
    _f("filters.adx.period","int",14,"XAUPY_ADXPeriod",aliases=("ADXPeriod","InpADXPeriod"),minimum=2,maximum=200),
    _f("filters.adx.min","float",0.0,"XAUPY_ADXMin",aliases=("ADXMin","InpADXMin"),minimum=0,maximum=100),
    _f("filters.adx.max","float",100.0,"XAUPY_ADXMax",aliases=("ADXMax","InpADXMax"),minimum=0,maximum=100),

    _f("filters.atr.enabled","bool",False,"XAUPY_ATRFilterEnabled",aliases=("ATREnabled","InpATREnabled")),
    _f("filters.atr.timeframe","enum","M5","XAUPY_ATRTF",aliases=("ATRTF","InpATRTF"),enum=TIMEFRAME_OPTIONS),
    _f("filters.atr.period","int",14,"XAUPY_ATRPeriod",aliases=("ATRPeriod","InpATRPeriod"),minimum=2,maximum=200),
    _f("filters.atr.min_price_units","float",0.0,"XAUPY_ATRMin",aliases=("ATRMin","InpATRMin"),minimum=0,maximum=1000),
    _f("filters.atr.max_price_units","float",1000.0,"XAUPY_ATRMax",aliases=("ATRMax","InpATRMax"),minimum=0,maximum=10000),

    _f("filters.open.enabled","bool",False,"XAUPY_OpenFilterEnabled",aliases=("OpenFilterEnabled","InpOpenFilterEnabled")),
    _f("filters.open.reference_mode","enum","DAILY_OPEN","XAUPY_OpenReferenceMode",aliases=("OpenReferenceMode","InpOpenReferenceMode"),enum=OPEN_REFERENCE_MODES),
    _f("filters.open.buffer_price_units","float",0.0,"XAUPY_OpenBuffer",aliases=("OpenBuffer","InpOpenBuffer"),minimum=0,maximum=100),

    _f("entry.mode","enum","MARKET","XAUPY_EntryMode",aliases=("EntryMode","InpEntryMode"),enum=ENTRY_MODES),
    _f("entry.pending_buffer_price_units","float",0.10,"XAUPY_PendingBuffer",aliases=("PendingBuffer","InpPendingBuffer"),minimum=0,maximum=100),
    _f("entry.pending_expiration_minutes","int",5,"XAUPY_PendingExpirationMinutes",aliases=("PendingExpirationMinutes","InpPendingExpirationMinutes"),minimum=1,maximum=1440),
    _f("entry.cancel_on_opposite_setup","bool",True,"XAUPY_CancelOnOpposite",aliases=("CancelOnOpposite","InpCancelOnOpposite")),
    _f("entry.cancel_on_direction_change","bool",True,"XAUPY_CancelOnDirectionChange",aliases=("CancelOnDirectionChange","InpCancelOnDirectionChange")),
    _f("entry.max_signal_age_bars","int",2,"XAUPY_MaxSignalAgeBars",aliases=("MaxSignalAgeBars","InpMaxSignalAgeBars"),minimum=1,maximum=100),

    _f("risk.sizing_mode","enum","RISK_PERCENT","XAUPY_SizingMode",aliases=("SizingMode","InpSizingMode"),enum=SIZING_MODES),
    _f("risk.risk_percent","float",0.50,"XAUPY_RiskPercent",aliases=("RiskPercent","InpRiskPercent"),minimum=0.01,maximum=10),
    _f("risk.fixed_lot","float",0.01,"XAUPY_FixedLot",aliases=("FixedLot","InpFixedLot"),minimum=0.001,maximum=100),
    _f("risk.max_lot","float",0.10,"XAUPY_MaxLot",aliases=("MaxLot","InpMaxLot"),minimum=0.001,maximum=100),
    _f("risk.max_daily_loss_pct","float",2.0,"XAUPY_MaxDailyLossPct",aliases=("MaxDailyLossPct","InpMaxDailyLossPct"),minimum=0.1,maximum=50),
    _f("risk.max_trades_per_day","int",8,"XAUPY_MaxTradesPerDay",aliases=("MaxTradesPerDay","InpMaxTradesPerDay"),minimum=1,maximum=1000),
    _f("risk.max_open_positions","int",1,"XAUPY_MaxOpenPositions",aliases=("MaxOpenPositions","InpMaxOpenPositions"),minimum=1,maximum=100),
    _f("risk.cooldown_minutes","int",3,"XAUPY_CooldownMinutes",aliases=("CooldownMinutes","InpCooldownMinutes"),minimum=0,maximum=1440),
    _f("risk.max_consecutive_losses","int",3,"XAUPY_MaxConsecutiveLosses",aliases=("MaxConsecutiveLosses","InpMaxConsecutiveLosses"),minimum=1,maximum=100),
    _f("risk.stop_after_daily_target","bool",False,"XAUPY_StopAfterDailyTarget",aliases=("StopAfterDailyTarget","InpStopAfterDailyTarget")),
    _f("risk.daily_target_pct","float",2.0,"XAUPY_DailyTargetPct",aliases=("DailyTargetPct","InpDailyTargetPct"),minimum=0.1,maximum=100),

    _f("stop_loss.mode","enum","STRUCTURE","XAUPY_SLMode",aliases=("SLMode","InpSLMode"),enum=SL_MODES),
    _f("stop_loss.fixed_price_units","float",5.0,"XAUPY_SLFixed",aliases=("SLFixed","InpSLFixed"),minimum=0.01,maximum=1000),
    _f("stop_loss.atr_timeframe","enum","M5","XAUPY_SLATRTF",aliases=("SLATRTF","InpSLATRTF"),enum=TIMEFRAME_OPTIONS),
    _f("stop_loss.atr_period","int",14,"XAUPY_SLATRPeriod",aliases=("SLATRPeriod","InpSLATRPeriod"),minimum=2,maximum=200),
    _f("stop_loss.atr_multiplier","float",1.5,"XAUPY_SLATRMultiplier",aliases=("SLATRMultiplier","InpSLATRMultiplier"),minimum=0.01,maximum=100),
    _f("stop_loss.structure_timeframe","enum","M5","XAUPY_SLStructureTF",aliases=("SLStructureTF","InpSLStructureTF"),enum=TIMEFRAME_OPTIONS),
    _f("stop_loss.structure_lookback","int",3,"XAUPY_SLStructureLookback",aliases=("SLStructureLookback","InpSLStructureLookback"),minimum=1,maximum=500),
    _f("stop_loss.structure_buffer_price_units","float",0.30,"XAUPY_SLStructureBuffer",aliases=("SLStructureBuffer","InpSLStructureBuffer"),minimum=0,maximum=100),
    _f("stop_loss.min_price_units","float",0.50,"XAUPY_SLMin",aliases=("SLMin","InpSLMin"),minimum=0.01,maximum=1000),
    _f("stop_loss.max_price_units","float",20.0,"XAUPY_SLMax",aliases=("SLMax","InpSLMax"),minimum=0.01,maximum=10000),

    _f("take_profit.mode","enum","FIXED","XAUPY_TPMode",aliases=("TPMode","InpTPMode"),enum=TP_MODES),
    _f("take_profit.fixed_price_units","float",7.0,"XAUPY_TPFixed",aliases=("TPFixed","InpTPFixed"),minimum=0.01,maximum=10000),
    _f("take_profit.rr_ratio","float",1.5,"XAUPY_TPRR",aliases=("TPRR","InpTPRR"),minimum=0.1,maximum=100),
    _f("take_profit.dynamic.near_tp_distance","float",0.50,"XAUPY_TPNearDistance",aliases=("TPNearDistance","InpTPNearDistance"),minimum=0,maximum=100),
    _f("take_profit.dynamic.extend_use_z","bool",True,"XAUPY_TPExtendUseZ",aliases=("TPExtendUseZ","InpTPExtendUseZ")),
    _f("take_profit.dynamic.extend_use_rsi","bool",True,"XAUPY_TPExtendUseRSI",aliases=("TPExtendUseRSI","InpTPExtendUseRSI")),
    _f("take_profit.dynamic.extend_logic","enum","BOTH","XAUPY_TPExtendLogic",aliases=("TPExtendLogic","InpTPExtendLogic"),enum=EXTEND_LOGIC_OPTIONS),
    _f("take_profit.dynamic.exit_z_reverse_delta","float",0.50,"XAUPY_TPExitZReverseDelta",aliases=("TPExitZReverseDelta","InpTPExitZReverseDelta"),minimum=0,maximum=20),
    _f("take_profit.dynamic.exit_rsi_reverse_delta","float",4.0,"XAUPY_TPExitRSIReverseDelta",aliases=("TPExitRSIReverseDelta","InpTPExitRSIReverseDelta"),minimum=0,maximum=100),
    _f("take_profit.dynamic.lock_sl_at_original_tp","bool",True,"XAUPY_TPLockAtOriginal",aliases=("TPLockAtOriginal","InpTPLockAtOriginal")),
    _f("take_profit.dynamic.lock_profit_buffer","float",0.0,"XAUPY_TPLockProfitBuffer",aliases=("TPLockProfitBuffer","InpTPLockProfitBuffer"),minimum=0,maximum=100),
    _f("take_profit.dynamic.max_extension_price_units","float",10.0,"XAUPY_TPMaxExtension",aliases=("TPMaxExtension","InpTPMaxExtension"),minimum=0,maximum=10000),
    _f("take_profit.dynamic.max_extension_minutes","int",15,"XAUPY_TPMaxExtensionMinutes",aliases=("TPMaxExtensionMinutes","InpTPMaxExtensionMinutes"),minimum=1,maximum=1440),
    _f("take_profit.dynamic.emergency_server_tp_enabled","bool",True,"XAUPY_TPEmergencyEnabled",aliases=("TPEmergencyEnabled","InpTPEmergencyEnabled")),
    _f("take_profit.dynamic.emergency_server_tp_price_units","float",20.0,"XAUPY_TPEmergencyDistance",aliases=("TPEmergencyDistance","InpTPEmergencyDistance"),minimum=0.01,maximum=10000),

    _f("management.breakeven_enabled","bool",True,"XAUPY_BEEnabled",aliases=("BEEnabled","InpBEEnabled")),
    _f("management.breakeven_trigger_rr","float",1.0,"XAUPY_BETriggerRR",aliases=("BETriggerRR","InpBETriggerRR"),minimum=0,maximum=100),
    _f("management.breakeven_offset_price_units","float",0.10,"XAUPY_BEOffset",aliases=("BEOffset","InpBEOffset"),minimum=0,maximum=100),
    _f("management.partial_close_enabled","bool",False,"XAUPY_PartialEnabled",aliases=("PartialEnabled","InpPartialEnabled")),
    _f("management.partial_close_at_rr","float",1.0,"XAUPY_PartialAtRR",aliases=("PartialAtRR","InpPartialAtRR"),minimum=0.1,maximum=100),
    _f("management.partial_close_percent","float",50.0,"XAUPY_PartialPercent",aliases=("PartialPercent","InpPartialPercent"),minimum=1,maximum=99),
    _f("management.trailing_enabled","bool",False,"XAUPY_TrailingEnabled",aliases=("TrailingEnabled","InpTrailingEnabled")),
    _f("management.trailing_mode","enum","STRUCTURE","XAUPY_TrailingMode",aliases=("TrailingMode","InpTrailingMode"),enum=TRAILING_MODES),
    _f("management.trailing_atr_multiplier","float",1.0,"XAUPY_TrailingATRMultiplier",aliases=("TrailingATRMultiplier","InpTrailingATRMultiplier"),minimum=0.01,maximum=100),
    _f("management.trailing_structure_lookback","int",2,"XAUPY_TrailingStructureLookback",aliases=("TrailingStructureLookback","InpTrailingStructureLookback"),minimum=1,maximum=500),
    _f("management.trailing_step_price_units","float",0.20,"XAUPY_TrailingStep",aliases=("TrailingStep","InpTrailingStep"),minimum=0,maximum=100),
    _f("management.sl_tighten_mode","enum","OFF","XAUPY_SLTightenMode",aliases=("SLTightenMode","InpSLTightenMode"),enum=SL_TIGHTEN_MODES),

    _f("sessions.timezone","str","BROKER","XAUPY_SessionTimezone",aliases=("SessionTimezone","InpSessionTimezone")),
    _f("sessions.session1_enabled","bool",True,"XAUPY_Session1Enabled",aliases=("Session1Enabled","InpSession1Enabled")),
    _f("sessions.session1_start","time","07:00","XAUPY_Session1Start",aliases=("Session1Start","InpSession1Start")),
    _f("sessions.session1_end","time","17:00","XAUPY_Session1End",aliases=("Session1End","InpSession1End")),
    _f("sessions.session2_enabled","bool",True,"XAUPY_Session2Enabled",aliases=("Session2Enabled","InpSession2Enabled")),
    _f("sessions.session2_start","time","17:00","XAUPY_Session2Start",aliases=("Session2Start","InpSession2Start")),
    _f("sessions.session2_end","time","22:00","XAUPY_Session2End",aliases=("Session2End","InpSession2End")),
    _f("sessions.monday","bool",True,"XAUPY_Monday",aliases=("TradeMonday","InpTradeMonday")),
    _f("sessions.tuesday","bool",True,"XAUPY_Tuesday",aliases=("TradeTuesday","InpTradeTuesday")),
    _f("sessions.wednesday","bool",True,"XAUPY_Wednesday",aliases=("TradeWednesday","InpTradeWednesday")),
    _f("sessions.thursday","bool",True,"XAUPY_Thursday",aliases=("TradeThursday","InpTradeThursday")),
    _f("sessions.friday","bool",True,"XAUPY_Friday",aliases=("TradeFriday","InpTradeFriday")),
    _f("sessions.saturday","bool",False,"XAUPY_Saturday",aliases=("TradeSaturday","InpTradeSaturday")),
    _f("sessions.sunday","bool",False,"XAUPY_Sunday",aliases=("TradeSunday","InpTradeSunday")),
    _f("sessions.weekend_close_enabled","bool",False,"XAUPY_WeekendCloseEnabled",aliases=("WeekendCloseEnabled","InpWeekendCloseEnabled")),
    _f("sessions.weekend_close_minutes_before","int",30,"XAUPY_WeekendCloseMinutes",aliases=("WeekendCloseMinutes","InpWeekendCloseMinutes"),minimum=0,maximum=1440),

    _f("news.enabled","bool",False,"XAUPY_NewsEnabled",aliases=("NewsEnabled","InpNewsEnabled")),
    _f("news.minutes_before","int",15,"XAUPY_NewsMinutesBefore",aliases=("NewsMinutesBefore","InpNewsMinutesBefore"),minimum=0,maximum=1440),
    _f("news.minutes_after","int",15,"XAUPY_NewsMinutesAfter",aliases=("NewsMinutesAfter","InpNewsMinutesAfter"),minimum=0,maximum=1440),
    _f("news.high_impact_only","bool",True,"XAUPY_NewsHighImpactOnly",aliases=("NewsHighImpactOnly","InpNewsHighImpactOnly")),

    _f("costs.max_spread_price_units","float",0.50,"XAUPY_MaxSpread",aliases=("MaxSpread","InpMaxSpread"),minimum=0,maximum=100),
    _f("costs.max_commission_per_lot","float",20.0,"XAUPY_MaxCommissionPerLot",aliases=("MaxCommissionPerLot","InpMaxCommissionPerLot"),minimum=0,maximum=10000),
    _f("costs.min_net_rr","float",1.20,"XAUPY_MinNetRR",aliases=("MinNetRR","InpMinNetRR"),minimum=0,maximum=100),
    _f("costs.max_slippage_points","int",30,"XAUPY_MaxSlippagePoints",aliases=("MaxSlippagePoints","InpMaxSlippagePoints"),minimum=0,maximum=100000),

    _f("execution.magic","int",991188,"XAUPY_Magic",aliases=("Magic","MagicNumber","InpMagic"),minimum=1,maximum=2147483647),
    _f("execution.order_comment","str","XAUPY","XAUPY_OrderComment",aliases=("OrderComment","InpOrderComment")),
    _f("execution.max_retry_count","int",0,"XAUPY_MaxRetryCount",aliases=("MaxRetryCount","InpMaxRetryCount"),minimum=0,maximum=0,locked_value=0),
    _f("execution.demo_only","bool",True,"XAUPY_DemoOnly",aliases=("DemoOnly","InpDemoOnly"),locked_value=True),
    _f("execution.allow_real_account","bool",False,"XAUPY_AllowRealAccount",aliases=("AllowRealAccount","InpAllowRealAccount"),locked_value=False),

    _f("safety.never_widen_sl","bool",True,"XAUPY_NeverWidenSL",aliases=("NeverWidenSL","InpNeverWidenSL"),locked_value=True),
    _f("safety.require_server_sl","bool",True,"XAUPY_RequireServerSL",aliases=("RequireServerSL","InpRequireServerSL"),locked_value=True),
    _f("safety.block_on_stale_market_data","bool",True,"XAUPY_BlockOnStaleData",aliases=("BlockOnStaleData","InpBlockOnStaleData"),locked_value=True),

    _f("logging.csv_enabled","bool",True,"XAUPY_CSVEnabled",aliases=("CSVEnabled","InpCSVEnabled")),
    _f("logging.decision_trace_enabled","bool",True,"XAUPY_DecisionTraceEnabled",aliases=("DecisionTraceEnabled","InpDecisionTraceEnabled")),
)


FIELD_BY_PATH = {field.path: field for field in FIELDS}

_ALIAS_TO_FIELD: dict[str, ConfigField] = {}
for _field in FIELDS:
    for _key in (_field.set_key, *_field.aliases):
        lowered = _key.casefold()
        if lowered in _ALIAS_TO_FIELD and _ALIAS_TO_FIELD[lowered] != _field:
            raise RuntimeError(f"duplicate .set alias: {_key}")
        _ALIAS_TO_FIELD[lowered] = _field


def field_for_set_key(key: str) -> ConfigField | None:
    return _ALIAS_TO_FIELD.get(key.strip().casefold())


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        node = current.get(part)
        if not isinstance(node, dict):
            node = {}
            current[part] = node
        current = node
    current[parts[-1]] = value


def get_path(target: dict[str, Any], path: str) -> Any:
    current: Any = target
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current


def default_profile() -> dict[str, Any]:
    profile: dict[str, Any] = {"schema_version": PROFILE_SCHEMA_VERSION}
    for field in FIELDS:
        _set_path(profile, field.path, deepcopy(field.default))
    return profile


def schema_payload() -> dict[str, Any]:
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "timeframe_options": list(TIMEFRAME_OPTIONS),
        "field_count": len(FIELDS),
        "fields": [field.public() for field in FIELDS],
    }


def coerce_value(field: ConfigField, raw: Any) -> Any:
    if field.kind == "str":
        if raw is None:
            return ""
        return str(raw)

    if field.kind == "time":
        value = str(raw).strip()
        if not _TIME_RE.match(value):
            raise ValueError("must be HH:MM in 24-hour format")
        return value

    if field.kind == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)) and raw in (0, 1):
            return bool(raw)
        value = str(raw).strip().casefold()
        if value in {"true", "1", "yes", "y", "on"}:
            return True
        if value in {"false", "0", "no", "n", "off"}:
            return False
        raise ValueError("must be boolean")

    if field.kind == "int":
        if isinstance(raw, bool):
            raise ValueError("must be integer")
        value = int(str(raw).strip()) if not isinstance(raw, int) else raw
        return value

    if field.kind == "float":
        if isinstance(raw, bool):
            raise ValueError("must be number")
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("must be finite")
        return value

    if field.kind == "enum":
        value = str(raw).strip().upper()
        lookup = {item.upper(): item for item in field.enum}
        if value not in lookup:
            raise ValueError(f"must be one of {field.enum}")
        return lookup[value]

    raise ValueError(f"unsupported field kind: {field.kind}")


def validate_profile(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not isinstance(profile, dict):
        return ["profile must be an object"]

    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {PROFILE_SCHEMA_VERSION}"
        )

    for field in FIELDS:
        try:
            raw = get_path(profile, field.path)
        except KeyError:
            errors.append(f"{field.path}: missing")
            continue

        try:
            value = coerce_value(field, raw)
        except (TypeError, ValueError) as exc:
            errors.append(f"{field.path}: {exc}")
            continue

        if field.minimum is not None and value < field.minimum:
            errors.append(f"{field.path}: must be >= {field.minimum}")
        if field.maximum is not None and value > field.maximum:
            errors.append(f"{field.path}: must be <= {field.maximum}")
        if field.locked_value is not None and value != field.locked_value:
            errors.append(
                f"{field.path}: locked safety value must be {field.locked_value!r}"
            )

    def check_order(low_path: str, high_path: str, message: str) -> None:
        try:
            low = float(get_path(profile, low_path))
            high = float(get_path(profile, high_path))
            if low > high:
                errors.append(message)
        except (KeyError, TypeError, ValueError):
            pass

    check_order(
        "pullback.rsi_buy_level",
        "pullback.rsi_sell_level",
        "pullback RSI buy level must be <= sell level",
    )
    check_order("filters.adx.min","filters.adx.max","ADX min must be <= ADX max")
    check_order(
        "filters.atr.min_price_units",
        "filters.atr.max_price_units",
        "ATR min must be <= ATR max",
    )
    check_order(
        "stop_loss.min_price_units",
        "stop_loss.max_price_units",
        "SL min must be <= SL max",
    )

    try:
        if float(get_path(profile, "risk.fixed_lot")) > float(get_path(profile, "risk.max_lot")):
            errors.append("risk.fixed_lot must be <= risk.max_lot")
    except (KeyError, TypeError, ValueError):
        pass

    return errors


def normalized_profile(profile: dict[str, Any]) -> dict[str, Any]:
    errors = validate_profile(profile)
    if errors:
        raise ValueError("; ".join(errors))

    result = {"schema_version": PROFILE_SCHEMA_VERSION}
    for field in FIELDS:
        _set_path(result, field.path, coerce_value(field, get_path(profile, field.path)))
    return result


def update_profile_value(profile: dict[str, Any], field: ConfigField, raw: Any) -> Any:
    value = coerce_value(field, raw)
    _set_path(profile, field.path, value)
    return value


def format_set_value(field: ConfigField, value: Any) -> str:
    value = coerce_value(field, value)
    if field.kind == "bool":
        return "true" if value else "false"
    if field.kind == "float":
        return format(value, ".12g")
    return str(value)
