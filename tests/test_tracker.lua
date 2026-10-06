local repo, home = arg[1], arg[2]
local getenv = os.getenv
os.getenv = function(name)
  if name == "HOME" then
    return home
  elseif name == "XDG_STATE_HOME" then
    return home .. "/state"
  end
  return getenv(name)
end

local binds = {}
local native_unbind_calls = 0
hl = {
  dsp = {
    exec_cmd = function(command)
      return { command = command }
    end,
  },
}

hl.bind = function(keys, dispatcher, options)
  local bind = { keys = keys, dispatcher = dispatcher, options = options, active = true }
  function bind:unbind()
    self.active = false
  end
  table.insert(binds, bind)
  return bind
end
hl.unbind = function(keys)
  native_unbind_calls = native_unbind_calls + 1
  for _, bind in ipairs(binds) do
    if bind.keys == keys then
      bind:unbind()
    end
  end
end

local function restore_helpers()
  o = {
    bind = function(keys, description, dispatcher, options)
      local opts = options or {}
      opts.description = description
      hl.bind(keys, dispatcher, opts)
    end,
  }
end

local function active_binds(keys, recording)
  local result = {}
  for _, bind in ipairs(binds) do
    local is_recording = type(bind.dispatcher) == "table" and bind.dispatcher.command ~= nil
    if bind.active and bind.keys == keys and is_recording == recording then
      table.insert(result, bind)
    end
  end
  return result
end

local function read_catalog()
  local file = assert(io.open(home .. "/state/hypr-shortcut-tracker/bindings.tsv"))
  local rows = {}
  for line in file:lines() do
    local keys, description = line:match("^(.-)\t(.*)$")
    assert(keys and not rows[keys], "duplicate or malformed catalog row: " .. line)
    rows[keys] = description
  end
  file:close()
  return rows
end

restore_helpers()
local tracker = dofile(repo .. "/lua/shortcut_tracker.lua")
tracker.start()
tracker.start()

local repeat_options = { repeating = true, locked = true, non_consuming = true }
o.bind("XF86AudioRaiseVolume", "Volume up", "volume", repeat_options)
local recorded = active_binds("XF86AudioRaiseVolume", true)
assert(#recorded == 1)
assert(not recorded[1].options.repeating)
assert(recorded[1].options.locked and recorded[1].options.non_consuming)
assert(not recorded[1].options.description)
assert(recorded[1].options ~= repeat_options)
assert(active_binds("XF86AudioRaiseVolume", false)[1].options.repeating)
assert(recorded[1].dispatcher.command:find("'\\''", 1, true), "home path must be shell-quoted")
assert(recorded[1].dispatcher.command:find(" record --key 'XF86AudioRaiseVolume'", 1, true))
assert(os.execute(recorded[1].dispatcher.command), "generated recorder command must execute")

o.bind("F9", "Stop dictation", "stop", { release = true })
o.bind("F9", "Start dictation", "start")
o.bind("F9", "Start dictation", "another")
recorded = active_binds("F9", true)
assert(#recorded == 1 and not recorded[1].options.release)
assert(#active_binds("F9", false) == 3)

o.bind("ReleaseOnly", "Release action", "release", { release = true })
assert(active_binds("ReleaseOnly", true)[1].options.release)
o.bind("LongThenShort", "Long press", "long", { long_press = true })
o.bind("LongThenShort", "Short press", "short")
recorded = active_binds("LongThenShort", true)
assert(#recorded == 1 and not recorded[1].options.long_press)
assert(active_binds("LongThenShort", false)[1].options.long_press)
o.bind("LongOnly", "Long action", "long", { long_press = true })
assert(active_binds("LongOnly", true)[1].options.long_press)
o.bind("ALT + TAB", "Cycle window", "cycle")
o.bind("ALT + TAB", "Reveal window", "reveal")
assert(#active_binds("ALT + TAB", true) == 1)
assert(#active_binds("ALT + TAB", false) == 2)
o.bind("SUPER + mouse:272", "Move window", "drag", { mouse = true })
assert(active_binds("SUPER + mouse:272", true)[1].options.mouse)
assert(active_binds("SUPER + mouse:272", false)[1].options.mouse)

o.bind("SUPER + X", "Old action", "old")
hl.unbind("SUPER + X")
assert(#active_binds("SUPER + X", true) == 0)
o.bind("SUPER + X", "New action", "new")
assert(#active_binds("SUPER + X", true) == 1)
tracker.finish()
local rows = read_catalog()
assert(rows["F9"] == "Stop dictation / Start dictation")
assert(rows["LongThenShort"] == "Long press / Short press")
assert(rows["ALT + TAB"] == "Cycle window / Reveal window")
assert(rows["SUPER + X"] == "New action")
assert(native_unbind_calls == 1)

local original_open = io.open
io.open = function(path, mode)
  if mode == "w" then
    return nil, "simulated write failure"
  end
  return original_open(path, mode)
end
local succeeded, error_message = pcall(tracker.finish)
io.open = original_open
assert(not succeeded and error_message:find("simulated write failure", 1, true))
assert(read_catalog()["F9"] == rows["F9"], "failed write must not replace catalog")

for _ = 1, 3 do
  binds = {}
  restore_helpers()
  tracker = dofile(repo .. "/lua/shortcut_tracker.lua")
  tracker.start()
  o.bind("SUPER + X", "Reload action", "reload")
  hl.unbind("SUPER + X")
  o.bind("SUPER + X", "Rebound action", "rebound")
  tracker.finish()
  assert(#active_binds("SUPER + X", true) == 1)
  assert(#active_binds("SUPER + X", false) == 1)
  assert(read_catalog()["SUPER + X"] == "Rebound action")
  assert(read_catalog()["F9"] == nil, "reload must replace the catalog")
end
assert(native_unbind_calls == 4, "unbind wrappers must not stack on reload")
