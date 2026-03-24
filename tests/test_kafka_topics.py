"""Kafka topic name constants stay stable and unique (contract for producers/consumers)."""

import shared_modules.kafka_event_bus.topics as topics


def test_topic_constants_are_non_empty_strings() -> None:
    names = [
        topics.CODE_PUSH,
        topics.GITOPS_PIPELINE,
        topics.CODE_ANALYSIS,
        topics.TEST_RESULTS,
        topics.BUILD_READY,
        topics.IAC_READY,
        topics.DEPLOYMENT_TRIGGERED,
        topics.OBSERVABILITY_ALERT,
        topics.ROLLBACK_EVENT,
    ]
    for n in names:
        assert isinstance(n, str)
        assert len(n) > 0


def test_topic_names_are_unique() -> None:
    names = [
        topics.CODE_PUSH,
        topics.GITOPS_PIPELINE,
        topics.CODE_ANALYSIS,
        topics.TEST_RESULTS,
        topics.BUILD_READY,
        topics.IAC_READY,
        topics.DEPLOYMENT_TRIGGERED,
        topics.OBSERVABILITY_ALERT,
        topics.ROLLBACK_EVENT,
    ]
    assert len(names) == len(set(names))
