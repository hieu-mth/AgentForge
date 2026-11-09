import argparse
import os
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from agentforge.model import generate


from agentforge.paths import REPOSITORY_ROOT

ROOT = REPOSITORY_ROOT
DB = ROOT / "data" / "checkpoints.sqlite"


class AgentState(TypedDict):
    task: str
    answer: str
    status: str


def reason(state: AgentState):
    answer = generate(state["task"])
    return {"answer": answer}


def finish(state: AgentState):
    if not state["answer"].strip():
        raise RuntimeError("Cannot finish an empty result")

    return {"status": "completed"}


def build_graph(checkpointer):
    builder = StateGraph(AgentState)

    builder.add_node("reason", reason)
    builder.add_node("finish", finish)

    builder.add_edge(START, "reason")
    builder.add_edge("reason", "finish")
    builder.add_edge("finish", END)

    return builder.compile(checkpointer=checkpointer)


def run_task(task: str):
    thread_id = uuid4().hex

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    DB.parent.mkdir(parents=True, exist_ok=True)

    with SqliteSaver.from_conn_string(str(DB)) as saver:
        graph = build_graph(saver)

        result = graph.invoke(
            {
                "task": task,
                "answer": "",
                "status": "pending"
            },
            config=config
        )

    print("TASK ID:", thread_id)
    print("STATUS:", result["status"])
    print("ANSWER:")
    print(result["answer"])


def show_status(thread_id: str):
    if not DB.exists():
        raise SystemExit("Checkpoint database not found")

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    with SqliteSaver.from_conn_string(str(DB)) as saver:
        graph = build_graph(saver)
        snapshot = graph.get_state(config)

    if not snapshot.values:
        raise SystemExit("Task ID not found")

    print("TASK ID:", thread_id)
    print("STATUS:", snapshot.values.get("status"))
    print("NEXT:", snapshot.next)
    print("ANSWER:", snapshot.values.get("answer", ""))


def main():
    parser = argparse.ArgumentParser(
        description="AgentForge Core"
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True
    )

    run = commands.add_parser("run")
    run.add_argument("task")

    status = commands.add_parser("status")
    status.add_argument("thread_id")

    args = parser.parse_args()

    if args.command == "run":
        run_task(args.task)

    elif args.command == "status":
        show_status(args.thread_id)
