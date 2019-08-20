import logging
from collections import defaultdict

from dagster import (
    ExecutionTargetHandle,
    ModeDefinition,
    PipelineDefinition,
    RunConfig,
    execute_pipeline,
    lambda_solid,
    pipeline,
)
from dagster.core.events import DagsterEventType, EventSink
from dagster.core.events.log import EventRecord, construct_event_logger
from dagster.loggers import colored_console_logger

from dagster_examples.toys.many_events import many_events


def mode_def(event_callback):
    return ModeDefinition(
        logger_defs={
            'callback': construct_event_logger(event_callback),
            'console': colored_console_logger,
        }
    )


def single_dagster_event(events, event_type):
    assert event_type in events
    return events[event_type][0]


def define_event_logging_pipeline(name, solids, event_callback, deps=None):
    return PipelineDefinition(
        name=name, solid_defs=solids, description=deps, mode_defs=[mode_def(event_callback)]
    )


def test_empty_pipeline():
    events = defaultdict(list)

    def _event_callback(record):
        assert isinstance(record, EventRecord)
        if record.is_dagster_event:
            events[record.dagster_event.event_type].append(record)

    pipeline_def = PipelineDefinition(
        name='empty_pipeline', solid_defs=[], mode_defs=[mode_def(_event_callback)]
    )

    result = execute_pipeline(pipeline_def, {'loggers': {'callback': {}, 'console': {}}})
    assert result.success
    assert events

    assert (
        single_dagster_event(events, DagsterEventType.PIPELINE_START).pipeline_name
        == 'empty_pipeline'
    )
    assert (
        single_dagster_event(events, DagsterEventType.PIPELINE_SUCCESS).pipeline_name
        == 'empty_pipeline'
    )


def test_single_solid_pipeline_success():
    events = defaultdict(list)

    @lambda_solid
    def solid_one():
        return 1

    def _event_callback(record):
        if record.is_dagster_event:
            events[record.dagster_event.event_type].append(record)

    pipeline_def = PipelineDefinition(
        name='single_solid_pipeline', solid_defs=[solid_one], mode_defs=[mode_def(_event_callback)]
    )

    result = execute_pipeline(pipeline_def, {'loggers': {'callback': {}}})
    assert result.success
    assert events

    start_event = single_dagster_event(events, DagsterEventType.STEP_START)
    assert start_event.pipeline_name == 'single_solid_pipeline'
    assert start_event.dagster_event.solid_name == 'solid_one'
    assert start_event.dagster_event.solid_definition_name == 'solid_one'

    output_event = single_dagster_event(events, DagsterEventType.STEP_OUTPUT)
    assert output_event
    assert output_event.dagster_event.step_output_data.output_name == 'result'
    assert output_event.dagster_event.step_output_data.intermediate_materialization is None

    success_event = single_dagster_event(events, DagsterEventType.STEP_SUCCESS)
    assert success_event.pipeline_name == 'single_solid_pipeline'
    assert success_event.dagster_event.solid_name == 'solid_one'
    assert success_event.dagster_event.solid_definition_name == 'solid_one'

    assert isinstance(success_event.dagster_event.step_success_data.duration_ms, float)
    assert success_event.dagster_event.step_success_data.duration_ms > 0.0


def test_single_solid_pipeline_failure():
    events = defaultdict(list)

    @lambda_solid
    def solid_one():
        raise Exception('nope')

    def _event_callback(record):
        if record.is_dagster_event:
            events[record.dagster_event.event_type].append(record)

    pipeline_def = PipelineDefinition(
        name='single_solid_pipeline', solid_defs=[solid_one], mode_defs=[mode_def(_event_callback)]
    )

    result = execute_pipeline(
        pipeline_def,
        {
            'loggers': {'callback': {}},
            'execution': {'in_process': {'config': {'raise_on_error': False}}},
        },
    )
    assert not result.success

    start_event = single_dagster_event(events, DagsterEventType.STEP_START)
    assert start_event.pipeline_name == 'single_solid_pipeline'

    assert start_event.dagster_event.solid_name == 'solid_one'
    assert start_event.dagster_event.solid_definition_name == 'solid_one'
    assert start_event.level == logging.DEBUG

    failure_event = single_dagster_event(events, DagsterEventType.STEP_FAILURE)
    assert failure_event.pipeline_name == 'single_solid_pipeline'

    assert failure_event.dagster_event.solid_name == 'solid_one'
    assert failure_event.dagster_event.solid_definition_name == 'solid_one'
    assert failure_event.level == logging.ERROR


def define_simple():
    @lambda_solid
    def yes():
        return 'yes'

    @pipeline
    def simple():
        yes()

    return simple


def test_event_sink_serialization():
    event_records = []

    class TestEventSink(EventSink):
        def on_dagster_event(self, dagster_event):
            event_records.append(dagster_event)

        def on_log_message(self, log_message):
            event_records.append(log_message)

    @lambda_solid
    def no():
        raise Exception('no')

    @pipeline
    def fails():
        no()

    sink = TestEventSink()

    # basic success
    execute_pipeline(define_simple(), run_config=RunConfig(event_sink=sink))
    # basic failure
    execute_pipeline(
        fails,
        run_config=RunConfig(event_sink=sink),
        environment_dict={'execution': {'in_process': {'config': {'raise_on_error': False}}}},
    )
    # multiproc
    execute_pipeline(
        ExecutionTargetHandle.for_pipeline_fn(define_simple).build_pipeline_definition(),
        run_config=RunConfig(event_sink=sink),
        environment_dict={'storage': {'filesystem': {}}, 'execution': {'multiprocess': {}}},
    )
    # kitchen sink
    execute_pipeline(many_events, run_config=RunConfig(event_sink=sink))

    for dagster_event in event_records:
        payload = dagster_event.to_json()
        clone = EventRecord.from_json(payload)
        assert clone == dagster_event
