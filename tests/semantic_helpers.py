"""Shared renderer/CLI comparisons with only the established normalization."""

import base64
from copy import deepcopy


def semantic_resource(document):
    result = deepcopy(document)
    # Never normalize pod labels, selectors, or ordered lists.
    for key in ("helm.sh/chart", "app.kubernetes.io/managed-by", "app.kubernetes.io/version"):
        result["metadata"]["labels"].pop(key, None)
    if result["kind"] == "Deployment":
        result["spec"]["template"]["spec"].setdefault("serviceAccountName", "default")
    if result["kind"] == "Secret":
        data = {key: base64.b64decode(value, validate=True)
                for key, value in result.pop("data", {}).items()}
        data.update({key: value.encode("utf-8")
                     for key, value in result.pop("stringData", {}).items()})
        result["data"] = data
    return result


def assert_semantically_equal(test, actual, expected):
    def identity(document):
        return document["kind"], document["metadata"]["name"]

    # Check multiplicity before indexing so duplicates cannot hide.
    test.assertCountEqual([identity(doc) for doc in actual], [identity(doc) for doc in expected])
    reference = {identity(doc): semantic_resource(doc) for doc in expected}
    test.assertEqual(len(reference), len(expected))
    for document in actual:
        with test.subTest(resource=identity(document)):
            test.assertEqual(semantic_resource(document), reference[identity(document)])
