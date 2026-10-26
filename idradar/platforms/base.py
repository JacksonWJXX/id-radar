"""统一状态和名字比对，完全同名优先。"""

from dataclasses import asdict, dataclass, field
from typing import Literal
import unicodedata

Status = Literal["available", "similar", "taken", "manual", "login", "blocked", "error", "invalid", "stopped"]


@dataclass
class Result:
    status: Status
    matches: list[dict] = field(default_factory=list)
    search_url: str = ""
    note: str = ""

    def to_dict(self):
        return asdict(self)


class Checker:
    id = ""
    label = ""
    mode = "auto"

    async def check(self, name: str, handle: str) -> Result:
        raise NotImplementedError


def normalize(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).split()).casefold()


def distance_one(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1 or left == right:
        return False
    if len(left) > len(right):
        left, right = right, left
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    index = 0
    while index < len(left) and left[index] == right[index]:
        index += 1
    return left[index:] == right[index + 1:]


def compare_names(query: str, candidate: str) -> str | None:
    left, right = normalize(query), normalize(candidate)
    if not left or not right:
        return None
    if left == right:
        return "taken"
    if min(len(left), len(right)) >= 3 and (left in right or right in left or distance_one(left, right)):
        return "similar"
    return None


def match_results(name: str, accounts: list[dict], search_url: str, note="") -> Result:
    exact, similar = [], []
    seen = set()
    for account in accounts:
        key = (account["name"], account.get("url", ""))
        if key in seen:
            continue
        seen.add(key)
        status = compare_names(name, account["name"])
        if status == "taken":
            exact.append(account)
        elif status == "similar":
            similar.append(account)
    return Result("taken" if exact else "similar" if similar else "available", (exact + similar)[:5], search_url, note)
