"""纯评分函数：可用数降序、占用数升序，再按原顺序。"""


def rank_rows(rows):
    scores = [{"row": index, "available": sum(value["status"] == "available" for value in results.values()),
               "taken": sum(value["status"] == "taken" for value in results.values())} for index, results in enumerate(rows)]
    return sorted(scores, key=lambda score: (-score["available"], score["taken"], score["row"]))
