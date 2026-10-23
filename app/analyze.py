"""后台跑完整分析链：打标 → 评分 → 连拍精选 → 人物分组 → 地点聚合。

以前 /api/analyze 是个同步长请求，1700 张要跑十分钟以上：连接一断整轮白跑、
全程看不到进度。这里照 scanner.ScanJob 的做法改成后台任务 + 进度轮询，
随时能看跑到哪一步，也能取消。
"""
import time

from . import ai, db, geo, people, quality, scanner

# (步骤标识, 界面上显示的中文名)
STEPS = [("tag", "打标"), ("warm", "缩略图预热"), ("score", "画质评分"), ("burst", "连拍精选"),
         ("people", "人物分组"), ("geo", "地点聚合")]


class Cancelled(Exception):
    """分析被取消：由进度回调抛出，让各步骤尽快退出。"""


class AnalyzeJob:
    def __init__(self):
        self.status = "running"          # running | done | cancelled | error
        self.step = ""
        self.step_index = 0
        self.total = 0
        self.done = 0
        self.rate = 0.0                  # 当前这一步的每秒处理张数
        self.step_started = time.time()
        self.result = {}
        self.error = None
        self.started_at = time.time()
        self.finished_at = None

    def progress(self, done, total):
        """各步骤在循环里每张回调一次，顺便当取消检查点。"""
        if total:
            self.total, self.done = total, done
        el = time.time() - self.step_started
        self.rate = done / el if el >= 0.1 else 0.0
        if self.status == "cancelled":
            raise Cancelled()

    def to_dict(self):
        return {"status": self.status, "step": self.step, "step_index": self.step_index,
                "steps": len(STEPS), "steps_list": [s[1] for s in STEPS],
                "total": self.total, "done": self.done, "rate": round(self.rate, 1),
                "result": self.result,
                "error": self.error, "started_at": self.started_at,
                "finished_at": self.finished_at}


def run_analyze(job, force=False):
    try:
        for i, (key, label) in enumerate(STEPS):
            job.step_index, job.step = i + 1, label
            job.total = job.done = 0
            job.rate = 0.0
            job.step_started = time.time()
            p = job.progress
            if key == "tag":
                job.result["tagged"] = ai.tag_all(progress=p)
                # 标签变了，关键词索引要跟着重建（几千张只要几十毫秒）
                db.fts_rebuild()
            elif key == "warm":
                job.result["warmed"] = scanner.warm_thumbs(progress=p)
            elif key == "score":
                job.result["scored"] = quality.score_all(progress=p)
            elif key == "burst":
                job.result["bursts"] = quality.group_bursts(progress=p)
            elif key == "people":
                job.result["people"] = people.analyze(progress=p, force=force)
            elif key == "geo":
                job.result["places"] = geo.rebuild(progress=p)
        job.result["ai"] = ai.ai_status()
        if job.status == "running":
            job.status = "done"
    except Cancelled:
        job.status = "cancelled"
    except Exception as e:
        job.status = "error"
        job.error = f"{type(e).__name__}: {e}"
    finally:
        job.finished_at = time.time()
