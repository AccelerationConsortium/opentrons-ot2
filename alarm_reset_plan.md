# Alarm State & Reset — Implementation Plan

## io/motion.py — OT2MotionController

Add two methods:

```python
async def reset_from_error(self) -> None:
    await self._driver._reset_from_error()

async def smoothie_reset(self) -> None:
    await self._driver._smoothie_reset()
```

## features/motion_control.py — MotionControlFeature

### New commands

```python
@sila.UnobservableCommand()
async def reset_from_error(self) -> HomedFlags:
    """Clear alarm lock state (M999). Returns homed flags after reset."""
    await self._controller.reset_from_error()
    return self.homed_flags

@sila.UnobservableCommand()
async def smoothie_reset(self) -> HomedFlags:
    """Full hardware GPIO reset of the Smoothie. Returns homed flags after reset."""
    await self._controller.smoothie_reset()
    return self.homed_flags
```

## Notes

- The driver silently swallows `error:Alarm lock` responses (`_handle_return` explicitly excludes them from raising). There is no reliable alarm state signal available without modifying the driver.
- `is_in_alarm` (homed_flags all-False) was rejected: indistinguishable from a never-homed-after-boot state.
- After `reset_from_error` or `smoothie_reset`, homed_flags will be all-False — operator must re-home before moving.
- `smoothie_reset` is more drastic (GPIO pin pulse); prefer `reset_from_error` for alarm recovery.
