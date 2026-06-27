# Completion Note

## Task

Test `claude --print <simple prompt>` and record whether it exits 0 and returns output on stdout.

## What was done

Ran `claude --print "say hi"` and captured exit code, stdout, and stderr separately.

## Result

- Exit code: `0`
- stdout: `Hi! How can I help you today?`
- stderr: empty

## Files touched

- `artifacts/3ad3e4de-0588-4323-bf6d-4c5eead62412/test_result.md` - full test output and conclusion

## Conclusion

`--print` is a valid flag. It exits 0 and delivers the model response cleanly on stdout. Safe to use in harness scripts.
