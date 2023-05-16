import json
from datetime import datetime
from typing import Dict, List, NewType, Optional, Union

from pydantic import BaseModel, Field, validator

Datetime = NewType("Datetime", datetime)


class ConnectRequest(BaseModel):

    uid: str
    sid: str
    created_at: Datetime = Field(default_factory=datetime.utcnow)

    @validator("created_at", pre=True, always=True)
    def set_datetime(cls, v):
        return v or datetime.utcnow()


class ActionResult(BaseModel):
    success: bool
    event: str
    message: Dict = {}


class Display(BaseModel):
    camera_x: Optional[int]
    camera_y: Optional[int]
    camera_z: Optional[int]
    x: int
    y: int


class Node(BaseModel):
    id: str
    name: str
    title: str
    description: str = ""
    properties: Dict = {}
    display: Display
    children: Optional[List[str]]
    child: Optional[str]
    tree: "Tree" = None


class Project(BaseModel):
    name: str
    data: Dict
    path: str


class Tree(BaseModel):
    version: str
    scope: str
    id: str
    title: str
    description: str = ""
    root: Union[str, None]
    properties: Dict = {}
    nodes: Dict[str, Node]
    display: Display

    def to_json(self, fname):
        """Saves the tree to a json file"""

        def cleandict(d):
            """Removes all the None fields"""
            if not isinstance(d, dict):
                return d
            return dict((k, cleandict(v)) for k, v in d.items() if v is not None)

        data = cleandict(self.dict())
        with open(fname, "w") as f:
            json.dump(data, f, indent=2)
