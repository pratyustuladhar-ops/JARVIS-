from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, HttpUrl


class BrowserOpenParams(BaseModel):
    session_id: Optional[str] = Field(None, description="Optional custom session identifier")
    browser_type: Optional[str] = Field("msedge", description="Browser to launch: msedge, chrome, or chromium")
    headless: Optional[bool] = Field(False, description="Run headless or visible")


class BrowserNavigateParams(BaseModel):
    url: str = Field(..., description="Target HTTP or HTTPS URL")
    session_id: Optional[str] = Field(None, description="Session identifier")
    timeout_ms: Optional[int] = Field(30000, ge=1000, le=60000, description="Navigation timeout in milliseconds")
    wait_until: Optional[str] = Field("domcontentloaded", description="Wait condition: domcontentloaded, load, or networkidle")


class BrowserGetPageInfoParams(BaseModel):
    session_id: Optional[str] = Field(None, description="Session identifier")


class BrowserFindElementParams(BaseModel):
    session_id: Optional[str] = Field(None, description="Session identifier")
    selector: Optional[str] = Field(None, description="CSS or locator selector")
    role: Optional[str] = Field(None, description="Accessible ARIA role (e.g. searchbox, button, textbox)")
    name: Optional[str] = Field(None, description="Accessible element name or label")
    text: Optional[str] = Field(None, description="Visible text to locate")
    timeout_ms: Optional[int] = Field(10000, ge=500, le=30000, description="Discovery timeout in ms")


class BrowserFillInputParams(BaseModel):
    text: str = Field(..., description="Text query or input to type into field")
    session_id: Optional[str] = Field(None, description="Session identifier")
    selector: Optional[str] = Field(None, description="CSS or locator selector for input")
    role: Optional[str] = Field(None, description="Accessible ARIA role")
    name: Optional[str] = Field(None, description="Accessible name/label")
    clear_first: Optional[bool] = Field(True, description="Clear existing text before filling")
    timeout_ms: Optional[int] = Field(10000, ge=500, le=30000, description="Fill timeout in ms")


class BrowserClickElementParams(BaseModel):
    session_id: Optional[str] = Field(None, description="Session identifier")
    selector: Optional[str] = Field(None, description="CSS or locator selector to click")
    role: Optional[str] = Field(None, description="Accessible ARIA role")
    name: Optional[str] = Field(None, description="Accessible name/label")
    text: Optional[str] = Field(None, description="Visible text")
    timeout_ms: Optional[int] = Field(10000, ge=500, le=30000, description="Click timeout in ms")


class BrowserPressKeyParams(BaseModel):
    key: str = Field(..., description="Keyboard key to press (e.g. Enter, Tab, Escape)")
    session_id: Optional[str] = Field(None, description="Session identifier")
    selector: Optional[str] = Field(None, description="Optional target element selector to focus before pressing")
    timeout_ms: Optional[int] = Field(10000, ge=500, le=30000, description="Key press timeout in ms")


class BrowserGetTextParams(BaseModel):
    session_id: Optional[str] = Field(None, description="Session identifier")
    selector: Optional[str] = Field(None, description="CSS or locator selector from which to extract text")
    max_chars: Optional[int] = Field(2000, ge=10, le=10000, description="Maximum characters to extract")
    timeout_ms: Optional[int] = Field(10000, ge=500, le=30000, description="Text extraction timeout in ms")


class BrowserWaitForStateParams(BaseModel):
    session_id: Optional[str] = Field(None, description="Session identifier")
    state: Optional[str] = Field("networkidle", description="Condition: networkidle, domcontentloaded, load, or visible")
    selector: Optional[str] = Field(None, description="Element selector to wait for")
    timeout_ms: Optional[int] = Field(15000, ge=500, le=45000, description="Wait timeout in ms")


class BrowserCloseParams(BaseModel):
    session_id: Optional[str] = Field(None, description="Session identifier")


class BrowserActionResult(BaseModel):
    status: str = "SUCCESS"  # SUCCESS, FAILED, TIMEOUT, BLOCKED
    session_id: str
    action: str
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    verified: bool = False
