# claude --print Test Result

## Command

```
claude --print "say hi"
```

## Results

| Field | Value |
|-------|-------|
| Exit code | `0` |
| stdout | `Hi! How can I help you today?` |
| stderr | (empty) |

## Conclusion

`--print` is a valid flag. Claude exits 0 and returns the model response on stdout with no stderr output. This confirms `--print` is suitable for use in harness scripts that capture output programmatically.
