"""Read-only log analytics and isolated, clearly labeled synthetic demo data."""
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException, Query, Request

router=APIRouter(prefix='/api/analytics')


@router.get('')
def analytics(request:Request,source:Literal['real','demo']='demo',
              period:Literal['hour','day','month']='day',
              date:Optional[str]=Query(None,regex=r'^\d{4}-\d{2}-\d{2}$'),hour:int=Query(9,ge=0,le=23)):
    try:
        return request.app.state.analytics.view(source,period,date,hour)
    except ValueError:
        raise HTTPException(422,'날짜·기간을 확인해 주세요.')
