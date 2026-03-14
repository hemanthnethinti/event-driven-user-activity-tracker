# Test Suite Notes

- Unit tests live inside each service:
  - `producer-service/tests`
  - `consumer-service/tests`
- Integration tests also live in those service test directories and are marked with `@pytest.mark.integration`.
- Integration tests are skipped unless `RUN_INTEGRATION_TESTS=1` is provided.
