# SPDX-License-Identifier: GPL-3.0-or-later
# Store (autoload): one-time unlocks through Stripe Checkout and the shared Hartmann Studios license server (/v2).
#
# No Stripe key and no card details ever touch the game. The flow, the same as the studio's other apps:
#   1. checkout(product, email) asks the server for a Stripe Checkout page and opens it in the person's browser.
#   2. The game asks the server every few seconds whether that session is paid; the server checks with Stripe itself.
#   3. The answer (what you own, a signed license) is kept in user://license.json. restore(email) asks again by email.
# Offline, a license keeps working until 14 days past its expiry.
extends Node

signal owned_changed
signal catalog_loaded
signal message(text: String, kind: String)
signal waiting_changed

const APP := "rotline"
const OFFLINE_GRACE := 14 * 24 * 3600
const DEFAULT_URL := "https://livecaptionn-premium.charles-h-hartmann1.workers.dev"
const UA := "HartmannStudios-Luma/1.0 Rotline"

var base_url = DEFAULT_URL
var path = "user://license.json"
var state: Dictionary = {}
var catalog: Dictionary = {}       # product key -> {label, amount, interval, trial_days, mode, promo_codes}
var catalog_error = ""
var catalog_loading = false
var waiting_for = ""              # a Checkout session id being watched
var waiting_product = ""
var opened: Array = []             # checkout addresses opened (the tests read this)
var open_in_browser = true
var _poll_left = 0.0
var _poll_timer: Timer


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	if OS.has_environment("HS_BILLING_URL"):
		base_url = OS.get_environment("HS_BILLING_URL").trim_suffix("/")
	if OS.has_environment("ROTLINE_LICENSE"):
		path = OS.get_environment("ROTLINE_LICENSE")
	_load()
	_poll_timer = Timer.new()
	_poll_timer.wait_time = 3.0
	_poll_timer.timeout.connect(_poll)
	add_child(_poll_timer)
	if email() != "" and Time.get_unix_time_from_system() >= float(state.get("revalidate_after", 0)):
		restore(email(), true)


# ------------------------------------------------------------------------------------------------ what you own
func entitlements() -> Array:
	var exp = int(state.get("license_exp", 0))
	if exp > 0 and Time.get_unix_time_from_system() > exp + OFFLINE_GRACE:
		return []
	return state.get("entitlements", [])


func owns(key: String) -> bool:
	return Data.owns(entitlements(), key)


func email() -> String:
	return str(state.get("email", ""))


func price(key: String) -> String:
	return Data.price_words(catalog[key]) if catalog.has(key) else ""


func _load() -> void:
	state = {}
	if FileAccess.file_exists(path):
		var f = FileAccess.open(path, FileAccess.READ)
		if f:
			var doc = JSON.parse_string(f.get_as_text())
			if doc is Dictionary:
				state = doc


func _save() -> void:
	var f = FileAccess.open(path, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(state))


func _store(doc: Dictionary, mail: String) -> void:
	var token = str(doc.get("licenseToken", ""))
	state["email"] = str(doc.get("email", "")) if doc.get("email") else (mail if mail != "" else email())
	state["entitlements"] = (doc.get("entitlements", []) as Array).map(func(x): return str(x))
	state["license"] = token
	state["license_exp"] = token_exp(token)
	state["revalidate_after"] = float(doc.get("revalidateAfter", 0) if doc.get("revalidateAfter") != null else 0)
	state["checked"] = Time.get_unix_time_from_system()
	_save()
	owned_changed.emit()


static func token_exp(token: String) -> int:
	# The exp in a license token's payload (base64url JSON before the first dot); 0 when unreadable.
	if token == "":
		return 0
	var body = token.split(".")[0].replace("-", "+").replace("_", "/")
	while body.length() % 4 != 0:
		body += "="
	var raw = Marshalls.base64_to_raw(body)
	var doc = JSON.parse_string(raw.get_string_from_utf8())
	return int(doc.get("exp", 0)) if doc is Dictionary else 0


static func valid_email(text: String) -> bool:
	var re = RegEx.create_from_string("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")
	return re.search(text.strip_edges()) != null


# ------------------------------------------------------------------------------------------------ talking to the server
func _request(method: int, route: String, body = null) -> Dictionary:
	# Returns {"ok": bool, "doc": {}, "error": "", "code": ""}. Awaitable.
	var http = HTTPRequest.new()
	http.timeout = 20.0
	add_child(http)
	var headers = ["Content-Type: application/json", "Accept: application/json", "User-Agent: " + UA]
	var payload = "" if body == null else JSON.stringify(body)
	var err = http.request(base_url + route, headers, method, payload)
	if err != OK:
		http.queue_free()
		return {"ok": false, "doc": {}, "error": "Couldn't reach the store. Check your connection and try again.", "code": "offline"}
	var res: Array = await http.request_completed
	http.queue_free()
	var result: int = res[0]
	var status: int = res[1]
	var raw: PackedByteArray = res[3]
	if result != HTTPRequest.RESULT_SUCCESS:
		return {"ok": false, "doc": {}, "error": "Couldn't reach the store. Check your connection and try again.", "code": "offline"}
	var doc = JSON.parse_string(raw.get_string_from_utf8())
	if not doc is Dictionary:
		doc = {}
	if status == 429:
		return {"ok": false, "doc": doc, "error": "Too many tries for now. Try again later.", "code": "rate_limited"}
	if status >= 400 or (doc.has("error") and not doc.get("entitlements")):
		var msg = str(doc.get("error", "The store answered with an error (%d)." % status))
		var code = str(doc.get("code", ""))
		if code == "" and "Unknown app" in msg:
			code = "unknown_app"
		if code == "unknown_app":
			msg = "Purchases aren't open yet. Everything else plays as normal."
		return {"ok": false, "doc": doc, "error": msg, "code": code if code != "" else "error"}
	return {"ok": true, "doc": doc, "error": "", "code": ""}


func load_catalog() -> void:
	if catalog_loading:
		return
	catalog_loading = true
	var r = await _request(HTTPClient.METHOD_GET, "/v2/catalog?app=" + APP)
	catalog_loading = false
	if r.ok:
		catalog = {}
		var products: Dictionary = r.doc.get("products", {})
		for key in products:
			var p: Dictionary = products[key]
			var d = p.get("display")
			if not d is Dictionary:
				d = {"label": str(d if d else key)}
			catalog[key] = {"label": d.get("label", key), "amount": d.get("amount"), "interval": d.get("interval"),
				"trial_days": int(p.get("trial_days", 0) if p.get("trial_days") != null else 0), "mode": str(p.get("mode", "")),
				"promo_codes": bool(p.get("promotion_codes", false) or d.get("promotion_codes", false))}
		catalog_error = "" if not catalog.is_empty() else "Nothing to buy right now."
	else:
		catalog_error = r.error
	catalog_loaded.emit()


func buy(product: String, mail: String) -> void:
	mail = mail.strip_edges()
	if not valid_email(mail):
		message.emit("Enter the email you want your receipt sent to.", "error")
		return
	var r = await _request(HTTPClient.METHOD_POST, "/v2/checkout", {"app": APP, "product": product, "email": mail})
	if not r.ok:
		message.emit(r.error, "error")
		return
	var url = str(r.doc.get("checkoutUrl", ""))
	if not url.begins_with("https://"):
		message.emit("Couldn't open checkout. Try again.", "error")
		return
	state["pending_email"] = mail
	opened.append(url)
	if open_in_browser:
		OS.shell_open(url)
	var m = RegEx.create_from_string("cs_(?:live|test)_[A-Za-z0-9]+").search(url)
	if m == null:
		message.emit("Finish paying in your browser, then use Restore purchases.", "info")
		return
	waiting_for = m.get_string()
	waiting_product = product
	_poll_left = 30 * 60
	_poll_timer.start()
	waiting_changed.emit()


func cancel_wait() -> void:
	waiting_for = ""
	_poll_timer.stop()
	waiting_changed.emit()


func _poll() -> void:
	if waiting_for == "":
		_poll_timer.stop()
		return
	_poll_left -= _poll_timer.wait_time
	if _poll_left <= 0:
		cancel_wait()
		message.emit("Still waiting on the payment. If you paid, use Restore purchases in a minute.", "info")
		return
	var session = waiting_for
	var r = await _request(HTTPClient.METHOD_POST, "/v2/entitlement", {"app": APP, "sessionId": session})
	if session != waiting_for:
		return
	if r.ok and (r.doc.get("entitlements", []) as Array).size() > 0:
		_store(r.doc, str(state.get("pending_email", "")))
		var name = str(Data.item(waiting_product).get("name", "Your purchase"))
		cancel_wait()
		message.emit(name + " is unlocked. Thank you!", "done")
	elif not r.ok and r.code in ["rate_limited", "unknown_app"]:
		cancel_wait()
		message.emit(r.error, "error")


func restore(mail: String = "", quiet: bool = false) -> void:
	mail = (mail if mail != "" else email()).strip_edges()
	if not valid_email(mail):
		if not quiet:
			message.emit("Enter the email you used at checkout.", "error")
		return
	var r = await _request(HTTPClient.METHOD_POST, "/v2/entitlement", {"app": APP, "email": mail})
	if not r.ok or not r.doc.has("entitlements"):
		if not quiet:
			message.emit(r.error if r.error != "" else "Couldn't check your purchases.", "error")
		return
	_store(r.doc, mail)
	if quiet:
		return
	var have = Data.ITEMS.filter(func(it): return owns(it.key)).map(func(it): return it.name)
	if have.is_empty():
		message.emit("No purchases found for " + mail + ".", "info")
	else:
		message.emit("Restored: " + ", ".join(have) + ". Thank you!", "done")
