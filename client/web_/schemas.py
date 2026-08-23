"""
Pydantic 数据模型
定义请求参数和响应格式
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class RecordQueryParams(BaseModel):
    """领料记录查询参数"""
    card_no: Optional[str] = Field(default="", description="工号")
    user_name: Optional[str] = Field(default="", description="姓名")
    material_code: Optional[str] = Field(default="", description="物料编码")
    material_name: Optional[str] = Field(default="", description="物料名称")
    date_from: Optional[str] = Field(default="", description="起始日期")
    date_to: Optional[str] = Field(default="", description="截止日期")
    unreturned_only: Optional[bool] = Field(default=False, description="仅显示未归还")
    page: Optional[int] = Field(default=1, ge=1, description="页码")
    page_size: Optional[int] = Field(default=50, ge=1, le=200, description="每页条数")


class PaginatedResponse(BaseModel):
    """分页响应"""
    total: int
    page: int
    page_size: int
    total_pages: int
    records: List[dict]
