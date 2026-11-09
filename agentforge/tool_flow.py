from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from agentforge.gateway import execute_tool


from agentforge.paths import REPOSITORY_ROOT

ROOT = REPOSITORY_ROOT
DB = ROOT / "data" / "tool_integration.sqlite"


class ToolState(TypedDict):
    path: str
    content: str
    write_status: str
    verified: bool


def write_node(state: ToolState):
    result = execute_tool(
        "write_file",
        {
            "path": state["path"],
            "content": state["content"]
        }
    )

    return {"write_status": result["status"]}


def verify_node(state: ToolState):
    content = execute_tool(
        "read_file",
        {"path": state["path"]}
    )

    if content != state["content"]:
        raise RuntimeError("File verification failed")

    return {"verified": True}


def build_graph(checkpointer):
    builder = StateGraph(ToolState)

    builder.add_node("write", write_node)
    builder.add_node("verify", verify_node)

    builder.add_edge(START, "write")
    builder.add_edge("write", "verify")
    builder.add_edge("verify", END)

    return builder.compile(checkpointer=checkpointer)


def main():
    DB.parent.mkdir(parents=True, exist_ok=True)

    config = {
        "configurable": {
            "thread_id": uuid4().hex
        }
    }

    with SqliteSaver.from_conn_string(str(DB)) as saver:
        graph = build_graph(saver)

        result = graph.invoke(
            {
                "path": "checks/integration.txt",
                "content": "AgentForge integration works",
                "write_status": "",
                "verified": False
            },
            config=config
        )

        snapshot = graph.get_state(config)

    assert result["verified"] is True
    assert snapshot.values["verified"] is True
    assert not snapshot.next

    print("GRAPH + GATEWAY: PASS")
    print("WRITE STATUS:", result["write_status"])
    print("CHECKPOINT: PASS")


if __name__ == "__main__":
    main()
