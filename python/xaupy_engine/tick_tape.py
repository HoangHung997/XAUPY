"""Compact immutable quote sequence; keeps every observed quote and timestamp."""
from array import array
from bisect import bisect_left
import math


class TickTape:
    def __init__(self):
        self._time=array('q');self._bid=array('d');self._ask=array('d');self._continuous=array('b')
        self._start=0;self._stop=0;self._sealed=False

    def append(self,row):
        if self._sealed:raise ValueError('Tick tape is immutable')
        stamp,bid,ask,continuous=row.get('time_msc'),row.get('bid'),row.get('ask'),row.get('continuous',True)
        if type(stamp) is not int or stamp<=0 or (self._time and stamp<self._time[-1]):raise ValueError('Tick timestamps must be positive and nondecreasing')
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (bid,ask)) or ask<bid:raise ValueError('Tick bid/ask must be finite positive ordered quotes')
        if type(continuous) is not bool:raise ValueError('Tick continuity must be boolean')
        self._time.append(stamp);self._bid.append(bid);self._ask.append(ask);self._continuous.append(continuous);self._stop+=1

    def seal(self):
        self._sealed=True;return self

    def __len__(self):return self._stop-self._start

    def __getitem__(self,index):
        if isinstance(index,slice):return [self[i] for i in range(*index.indices(len(self))) ]
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        i=self._start+index
        return dict(time_msc=self._time[i],bid=self._bid[i],ask=self._ask[i],continuous=bool(self._continuous[i]))

    def __iter__(self):
        for i in range(self._start,self._stop):
            yield dict(time_msc=self._time[i],bid=self._bid[i],ask=self._ask[i],continuous=bool(self._continuous[i]))

    def timestamps(self):
        for i in range(self._start,self._stop):yield self._time[i]

    def between(self,first_msc,end_msc):
        """A zero-copy [first, end) view, including equal-millisecond quotes."""
        if not self._sealed:raise ValueError('Seal before selecting a view')
        result=object.__new__(TickTape)
        result._time=self._time
        result._bid=self._bid;result._ask=self._ask;result._continuous=self._continuous
        result._start=bisect_left(self._time,first_msc,self._start,self._stop)
        result._stop=bisect_left(self._time,end_msc,result._start,self._stop)
        result._sealed=True;return result
