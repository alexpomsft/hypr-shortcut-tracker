local tracker = {}

local home = os.getenv("HOME")
local state_home = os.getenv("XDG_STATE_HOME") or (home .. "/.local/state")
local state_dir = state_home .. "/hypr-shortcut-tracker"
local catalog_path = state_dir .. "/bindings.tsv"
local executable = home .. "/.local/bin/hypr-shortcuts"

local catalog = {}
local tracked_triggers = {}
local started = false

local raw_hl_bind = hl.bind
_G.__hypr_shortcut_tracker_raw_unbind =
  _G.__hypr_shortcut_tracker_raw_unbind or hl.unbind
local raw_hl_unbind = _G.__hypr_shortcut_tracker_raw_unbind

local function shell_quote(value)
  return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end

local function copy_options(options)
  local copy = {}
  for key, value in pairs(options or {}) do
    if key ~= "description" then
      copy[key] = value
    end
  end
  return copy
end

local function trigger_signature(keys, options)
  local opts = options or {}
  return table.concat({
    keys,
    opts.release and "release" or "press",
    opts.long_press and "long" or "short",
  }, "\t")
end

local function add_description(entry, description)
  if not description or description == "" or entry.seen[description] then
    return
  end
  entry.seen[description] = true
  table.insert(entry.descriptions, description)
end

local function remove_key(keys)
  for signature, entry in pairs(catalog) do
    if entry.keys == keys then
      catalog[signature] = nil
      tracked_triggers[signature] = nil
    end
  end
end

function tracker.start()
  if started then
    return
  end
  started = true

  local original_o_bind = o.bind

  hl.unbind = function(keys, ...)
    remove_key(keys)
    return raw_hl_unbind(keys, ...)
  end

  o.bind = function(keys, description, dispatcher, options)
    local signature = trigger_signature(keys, options)
    local entry = catalog[signature]
    if not entry then
      entry = {
        keys = keys,
        descriptions = {},
        seen = {},
      }
      catalog[signature] = entry
    end
    add_description(entry, description)

    if not tracked_triggers[signature] then
      local command = shell_quote(executable)
        .. " record --key "
        .. shell_quote(keys)
      raw_hl_bind(keys, hl.dsp.exec_cmd(command), copy_options(options))
      tracked_triggers[signature] = true
    end

    return original_o_bind(keys, description, dispatcher, options)
  end
end

function tracker.finish()
  os.execute("mkdir -p " .. shell_quote(state_dir))
  local temporary_path = catalog_path .. ".tmp"
  local file, error_message = io.open(temporary_path, "w")
  if not file then
    error("Could not write shortcut tracker catalog: " .. tostring(error_message))
  end

  local entries = {}
  for _, entry in pairs(catalog) do
    table.insert(entries, entry)
  end
  table.sort(entries, function(left, right)
    return left.keys < right.keys
  end)

  for _, entry in ipairs(entries) do
    local description = table.concat(entry.descriptions, " / ")
    description = description:gsub("[\t\r\n]", " ")
    file:write(entry.keys, "\t", description, "\n")
  end
  file:close()

  local renamed, rename_error = os.rename(temporary_path, catalog_path)
  if not renamed then
    error("Could not publish shortcut tracker catalog: " .. tostring(rename_error))
  end
end

return tracker

