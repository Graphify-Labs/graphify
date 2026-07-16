docReady(() => {
  if (!EVALEX_TRUSTED) {
    initPinBox();
  }
  // if we are in console mode, show the console.
  if (CONSOLE_MODE && EVALEX) {
    createInteractiveConsole();
  }

  const frames = document.querySelectorAll("div.traceback div.frame");
  if (EVALEX) {
    addConsoleIconToFrames(frames);
  }
  addEventListenersToElements(document.querySelectorAll("div.detail"), "click", () =>
    document.querySelector("div.traceback").scrollIntoView(false)
  );
  addToggleFrameTraceback(frames);
  addToggleTraceTypesOnClick(document.querySelectorAll("h2.traceback"));
  addInfoPrompt(document.querySelectorAll("span.nojavascript"));
  wrapPlainTraceback();
});

function addToggleFrameTraceback(frames) {
  frames.forEach((frame) => {
    frame.addEventListener("click", () => {
      frame.getElementsByTagName("pre")[0].parentElement.classList.toggle("expanded");
    });
  })
}


function wrapPlainTraceback() {
  const plainTraceback = document.querySelector("div.plain textarea");
  const wrapper = document.createElement("pre");
  const textNode = document.createTextNode(plainTraceback.textContent);
  wrapper.appendChild(textNode);
  plainTraceback.replaceWith(wrapper);
}

function makeDebugURL(args) {
  const params = new URLSearchParams(args)
  params.set("s", SECRET)
  return `?__debugger__=yes&${params}`
}

function initPinBox() {
  document.querySelector(".pin-prompt form").addEventListener(
    "submit",
    function (event) {
      event.preventDefault();
      const btn = this.btn;
      btn.disabled = true;

      fetch(
        makeDebugURL({cmd: "pinauth", pin: this.pin.value})
      )
        .then((res) => res.json())
        .then(({auth, exhausted}) => {
          if (auth) {
            EVALEX_TRUSTED = true;
            fadeOut(document.getElementsByClassName("pin-prompt")[0]);
          } else {
            alert(
              `Error: ${
                exhausted
                  ? "too many attempts.  Restart server to retry."
                  : "incorrect pin"
              }`
            );
          }
        })
        .catch((err) => {
          alert("Error: Could not verify PIN.  Network error?");
          console.error(err);
        })
        .finally(() => (btn.disabled = false));
    },
    false
  );
}

function promptForPin() {
  if (!EVALEX_TRUSTED) {
    fetch(makeDebugURL({cmd: "printpin"}));
    const pinPrompt = document.getElementsByClassName("pin-prompt")[0];
    fadeIn(pinPrompt);
    document.querySelector('.pin-prompt input[name="pin"]').focus();
  }
}

/**
 * Helper function for shell initialization
 */
function openShell(consoleNode, target, frameID) {
  promptForPin();
  if (consoleNode) {
    slideToggle(consoleNode);
    return consoleNode;
  }
  let historyPos = 0;
  const history = [""];
  const consoleElement = createConsole();
  const output = createConsoleOutput();
  const form = createConsoleInputForm();
  const command = createConsoleInput();

  target.parentNode.appendChild(consoleElement);
  consoleElement.append(output);
  consoleElement.append(form);
  form.append(command);
  command.focus();
  slideToggle(consoleElement);

  form.addEventListener("submit", (e) => {
    handleConsoleSubmit(e, command, frameID).then((consoleOutput) => {
      output.append(consoleOutput);
      command.focus();
      consoleElement.scrollTo(0, consoleElement.scrollHeight);
      const old = history.pop();
      history.push(command.value);
      if (typeof old !== "undefined") {
        history.push(old);
      }
      historyPos = history.length - 1;
      command.value = "";
    });
  });

  command.addEventListener("keydown", (e) => {
    if (e.key === "l" && e.ctrlKey) {
      output.innerText = "--- screen cleared ---";
    } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      // Handle up arrow and down arrow.
      if (e.key === "ArrowUp" && historyPos > 0) {
        e.preventDefault();
        historyPos--;
      } else if (e.key === "ArrowDown" && historyPos < history.length - 1) {
        historyPos++;
      }
      command.value = history[historyPos];
    }
    return false;
  });

  return consoleElement;
}

function addEventListenersToElements(elements, event, listener) {
  elements.forEach((el) => el.addEventListener(event, listener));
}

/**
 * Add extra info
 */
function addInfoPrompt(elements) {
  for (let i = 0; i < elements.length; i++) {
    elements[i].innerHTML =
      "<p>To switch between the interactive traceback and the plaintext " +
      'one, you can click on the "Traceback" headline. From the text ' +
      "traceback you can also create a paste of it. " +
      (!EVALEX
        ? ""
        : "For code execution mouse-over the frame you want to debug and " +
          "click on the console icon on the right side." +
          "<p>You can execute arbitrary Python code in the stack frames and " +
          "there are some extra helpers available for introspection:" +
          "<ul><li><code>dump()</code> shows all variables in the frame" +
          "<li><code>dump(obj)</code> dumps all that's known about the object</ul>");
    elements[i].classList.remove("nojavascript");
  }
}

function addConsoleIconToFrames(frames) {
  for (let i = 0; i < frames.length; i++) {
    let consoleNode = null;
    const target = frames[i];
    const frameID = frames[i].id.substring(6);

    for (let j = 0; j < target.getElementsByTagName("pre").length; j++) {
      const img = createIconForConsole();
      img.addEventListener("click", (e) => {
        e.stopPropagation();
        consoleNode = openShell(consoleNode, target, frameID);
        return false;
      });
      target.getElementsByTagName("pre")[j].append(img);
    }
  }
}

function slideToggle(target) {
  target.classList.toggle("active");
}

/**
 * toggle traceback types on click.
 */
function addToggleTraceTypesOnClick(elements) {
  for (let i = 0; i < elements.length; i++) {
    elements[i].addEventListener("click", () => {
      document.querySelector("div.traceback").classList.toggle("hidden");
      document.querySelector("div.plain").classList.toggle("hidden");
    });
    elements[i].style.cursor = "pointer";
    document.querySelector("div.plain").classList.toggle("hidden");
  }
}

function createConsole() {
  const consoleNode = document.createElement("pre");
  consoleNode.classList.add("console");
  consoleNode.classList.add("active");
  return consoleNode;
}

function createConsoleOutput() {
  const output = document.createElement("div");
  output.classList.add("output");
  output.innerHTML = "[console ready]";
  return output;
}

function createConsoleInputForm() {
  const form = document.createElement("form");
  form.innerHTML = "&gt;&gt;&gt; ";
  return form;
}

function createConsoleInput() {
  const command = document.createElement("input");
  command.type = "text";
  command.setAttribute("autocomplete", "off");
  command.setAttribute("spellcheck", false);
  command.setAttribute("autocapitalize", "off");
  command.setAttribute("autocorrect", "off");
  return command;
}

function createIconForConsole() {
  const img = document.createElement("img");
  img.setAttribute("src", makeDebugURL({cmd: "resource", f: "console.png"}));
  img.setAttribute("title", "Open an interactive python shell in this frame");
  return img;
}

function createExpansionButtonForConsole() {
  const expansionButton = document.createElement("a");
  expansionButton.setAttribute("href", "#");
  expansionButton.setAttribute("class", "toggle");
  expansionButton.innerHTML = "&nbsp;&nbsp;";
  return expansionButton;
}

function createInteractiveConsole() {
  const target = document.querySelector("div.console div.inner");
  while (target.firstChild) {
    target.removeChild(target.firstChild);
  }
  openShell(null, target, 0);
}

function handleConsoleSubmit(e, command, frameID) {
  // Prevent page from refreshing.
  e.preventDefault();

  return new Promise((resolve) => {
    fetch(makeDebugURL({cmd: command.value, frm: frameID}))
      .then((res) => {
        return res.text();
      })
      .then((data) => {
        const tmp = document.createElement("div");
        tmp.innerHTML = data;
        resolve(tmp);

        // Handle expandable span for long list outputs.
        // Example to test: list(range(13))
        let wrapperAdded = false;
        const wrapperSpan = document.createElement("span");
        const expansionButton = createExpansionButtonForConsole();

        tmp.querySelectorAll("span.extended").forEach((spanToWrap) => {
          const parentDiv = spanToWrap.parentNode;
          if (!wrapperAdded) {
            parentDiv.insertBefore(wrapperSpan, spanToWrap);
            wrapperAdded = true;
          }
          parentDiv.removeChild(spanToWrap);
          wrapperSpan.append(spanToWrap);
          spanToWrap.hidden = true;

          expansionButton.addEventListener("click", (event) => {
            event.preventDefault();
            spanToWrap.hidden = !spanToWrap.hidden;
            expansionButton.classList.toggle("open");
            return false;
          });
        });

        // Add expansion button at end of wrapper.
        if (wrapperAdded) {
          wrapperSpan.append(expansionButton);
        }
      })
      .catch((err) => {
        console.error(err);
      });
    return false;
  });
}

function fadeOut(element) {
  element.style.opacity = 1;

  (function fade() {
    element.style.opacity -= 0.1;
    if (element.style.opacity < 0) {
      element.style.display = "none";
    } else {
      requestAnimationFrame(fade);
    }
  })();
}

function fadeIn(element, display) {
  element.style.opacity = 0;
  element.style.display = display || "block";

  (function fade() {
    let val = parseFloat(element.style.opacity) + 0.1;
    if (val <= 1) {
      element.style.opacity = val;
      requestAnimationFrame(fade);
    }
  })();
}

function docReady(fn) {
  if (document.readyState === "complete" || document.readyState === "interactive") {
    setTimeout(fn, 1);
  } else {
    document.addEventListener("DOMContentLoaded", fn);
  }
}
