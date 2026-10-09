"""v3 contracts: blind judgments, hindsight and objective outcomes never mix."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

REASONS={'前期强势','回撤较充分','下跌尚未结束','出现承接迹象','已经开始转强','尚未真正转强','最近涨得过多','当前价格偏贵','当前价格位置合理','形态凌乱','无法判断'}
REVIEW_REASONS={'判断合理','入场偏贵','时机不对','假突破','继续下跌','回踩再涨','跳空风险','无法归因'}

class Contract(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)

class BlindRequest(Contract):
    version: Literal['h-blind-v3']
    task_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_revision: int=Field(ge=0)
    observe: Literal['观察','不观察','不确定']
    entry: Literal['当前可买','等回落或进一步确认','不买','不确定']
    confidence: Literal['高','中','低']
    reasons: list[str]=Field(default_factory=list,max_length=11)
    revision_reason: str=Field(default='',max_length=500)

    @field_validator('reasons')
    @classmethod
    def choices(cls,v):
        if len(v)!=len(set(v)) or not set(v)<=REASONS:raise ValueError('invalid blind reasons')
        return sorted(v)

class ReviewRequest(Contract):
    version: Literal['h-review-v3']
    task_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_revision: int=Field(ge=0)
    reasons: list[str]=Field(default_factory=list,max_length=8)
    note: str=Field(default='',max_length=1000)

    @field_validator('reasons')
    @classmethod
    def choices(cls,v):
        if len(v)!=len(set(v)) or not set(v)<=REVIEW_REASONS:raise ValueError('invalid review reasons')
        return sorted(v)

class NumericInput(Contract):
    version: Literal['x-left-num-v3']
    raw_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    normalized_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    tensor_sha256: str=Field(pattern=r'^[0-9a-f]{64}$')
    length: Literal[60,126]
    channels: Literal['open,high,low,close,volume']
    split: Literal['train','validation']

class VectorInput(Contract):
    version: Literal['x-left-svg-v3']
    renderer: Literal['shape-wrapper-blind-svg-v3']
    svg_sha256: str=Field(pattern=r'^[0-9a-f]{64}$')
    geometry_sha256: str=Field(pattern=r'^[0-9a-f]{64}$')
    numeric_hash: str=Field(pattern=r'^[0-9a-f]{64}$')

class FutureOutcome(Contract):
    version: Literal['y-future-v3']
    horizon: Literal[10]
    entry_reference: Literal['T+1 vendor-basis open; relative research proxy']
    target: Literal[0.05]
    adverse: Literal[-0.03]
    fee_bps: Literal[0]
    slippage_bps: Literal[0]
    status: Literal['available','unavailable','censored','ambiguous']
    event: Literal['target_first','adverse_first','both_same_bar','neither_hit','not_evaluable']
    event_day: int|None=Field(default=None,ge=1,le=10)
    entry_open: float|None=Field(default=None,gt=0)
    returns: dict[str,float|None]
    mfe: float|None=None
    mae: float|None=None
    new_low: bool|None=None
    conservative_event: Literal['adverse_first']|None=None
    flags: list[str]
    source_hash: str=Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def integrity(self):
        if set(self.returns)!={'1','3','5','10'}:raise ValueError('four fixed horizons required')
        if self.status=='available' and (self.entry_open is None or self.mfe is None or self.mae is None):raise ValueError('available outcome incomplete')
        if self.status=='ambiguous' and self.event!='both_same_bar':raise ValueError('ambiguous event contract')
        return self

class Annotation(Contract):
    task_id: str=Field(pattern=r'^[0-9a-f]{24}$')
    annotation_id: str=Field(pattern=r'^[0-9a-f]{32}$')
    origin: Literal['human','smoke']
    user_id: int=Field(ge=1)
    revision: int=Field(ge=1)
    created_at: str
    phase: Literal['blind','post_reveal_revision','review']
    contaminated_retest: bool
    payload: BlindRequest|ReviewRequest

    @field_validator('created_at')
    @classmethod
    def zoned(cls,v):
        if datetime.fromisoformat(v).tzinfo is None:raise ValueError('timezone required')
        return v

    @model_validator(mode='after')
    def phase_matches(self):
        if (self.phase=='review')!=isinstance(self.payload,ReviewRequest):raise ValueError('review cannot masquerade as blind')
        return self
