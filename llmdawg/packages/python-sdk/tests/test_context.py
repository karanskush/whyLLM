"""Tests for the context module (user_id, session_id, tags, trace)."""

from __future__ import annotations

from llmdawg.context import (
    clear_tags,
    get_context,
    set_session,
    set_tags,
    set_user,
    trace,
)


class TestSetters:
    def test_set_user(self):
        set_user("u-1")
        try:
            ctx = get_context()
            assert ctx["user_id"] == "u-1"
        finally:
            set_user(None)

    def test_set_session(self):
        set_session("s-1")
        try:
            ctx = get_context()
            assert ctx["session_id"] == "s-1"
        finally:
            set_session(None)

    def test_set_tags_merges(self):
        set_tags({"a": "1"})
        set_tags({"b": "2"})
        try:
            ctx = get_context()
            assert ctx["tags"]["a"] == "1"
            assert ctx["tags"]["b"] == "2"
        finally:
            clear_tags()

    def test_clear_tags(self):
        set_tags({"x": "y"})
        clear_tags()
        ctx = get_context()
        assert "tags" not in ctx

    def test_empty_context_returns_empty_dict(self):
        set_user(None)
        set_session(None)
        clear_tags()
        ctx = get_context()
        assert ctx == {}


class TestTrace:
    def test_trace_sets_trace_id(self):
        with trace(name="t1") as tid:
            ctx = get_context()
            assert ctx["trace_id"] == tid
            assert ctx["name"] == "t1"

    def test_trace_cleans_up(self):
        with trace(name="inner"):
            pass
        ctx = get_context()
        assert "trace_id" not in ctx
        assert "name" not in ctx

    def test_trace_user_scoped(self):
        set_user("outer-user")
        try:
            with trace(user_id="inner-user"):
                ctx = get_context()
                assert ctx["user_id"] == "inner-user"
            ctx = get_context()
            assert ctx["user_id"] == "outer-user"
        finally:
            set_user(None)

    def test_trace_tags_scoped(self):
        set_tags({"a": "1"})
        try:
            with trace(tags={"b": "2"}):
                ctx = get_context()
                assert ctx["tags"]["a"] == "1"
                assert ctx["tags"]["b"] == "2"
            ctx = get_context()
            assert ctx["tags"]["a"] == "1"
            assert "b" not in ctx["tags"]
        finally:
            clear_tags()

    def test_custom_trace_id(self):
        with trace(trace_id="custom-id") as tid:
            assert tid == "custom-id"
            ctx = get_context()
            assert ctx["trace_id"] == "custom-id"

    def test_nested_traces(self):
        with trace(name="outer") as outer_tid:
            with trace(name="inner") as inner_tid:
                ctx = get_context()
                assert ctx["trace_id"] == inner_tid
                assert ctx["name"] == "inner"
            ctx = get_context()
            assert ctx["trace_id"] == outer_tid
            assert ctx["name"] == "outer"
