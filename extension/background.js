var ws = null;

var addr = 'localhost:8888';

function sendMessage() {
    var input = document.getElementById('input').value;
    if (!input) {
        return;
    }
    document.getElementById('input').value = '';
    ws.send(input);
}

var retryIntervalMin = 1000;  // ms
var retryIntervalMax = 60 * 1000;
var retryInterval = retryIntervalMin;

function connectToServer() {
    console.log('connectToServer');
    var url = 'ws://' + addr + '/ws';
    ws = new WebSocket(url);
    ws.onmessage = onmessage;
    ws.onopen = onopen;
    ws.onclose = onclose;
    ws.onerror = onerror;
}

function init() {
    connectToServer();
}

function addMessage(message) {
    console.log(message);
}

function onerror(e) {
    addMessage('Encountered error.');
    addMessage(e)
}

var connectionOpened = false;

function onopen(e) {
    connectionOpened = true;
    retryInterval = retryIntervalMin;
    var popup = webkitNotifications.createNotification(
        "",  // no icon. Don't use null.
        "Notification",
        "Connected to the werver.");
    setTimeout(function() { popup.cancel(); }, 5000);
    popup.show();
}

function onclose(e) {
    if (connectionOpened) {
        var popup = webkitNotifications.createNotification(
            "",  // no icon. Don't use null.
            "Notification",
            "The connection was closed by the server.");
        setTimeout(function() { popup.cancel(); }, 5000);
        popup.show();
    } else {
        console.log('Failed to connect to the server.');
    }
    connectionOpened = false;
    setTimeout(connectToServer, retryInterval);
    retryInterval = retryInterval * 2;
    if (retryInterval > retryIntervalMax) {
        retryInterval = retryIntervalMax;
    }
}

function onmessage(e) {
    addMessage('Recieved: ' + e.data);
    var obj = JSON.parse(e.data);
    var cmd = obj['cmd'];
    var url = 'http://' + addr + obj['url'];
    if (cmd == 'show') {
        chrome.tabs.create({'url': url, 'selected': true});
    } else if (cmd == 'close') {
        chrome.tabs.getAllInWindow(null, function(tabs) {
            for (var i = 0; i < tabs.length; ++i) {
                if (tabs[i].url.indexOf(url) == 0) {
                    chrome.tabs.remove(tabs[i].id);
                }
            }
        });
    }
}
