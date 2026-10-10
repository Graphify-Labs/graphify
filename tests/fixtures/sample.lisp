(defpackage :http-server
  (:use :cl :alexandria)
  (:export #:make-server #:start #:stop))

(in-package :http-server)

(deftype port-number () '(integer 1 65535))

(defstruct request-stats
  bytes-in
  bytes-out
  duration-ms)

(defstruct (connection (:conc-name conn-))
  id
  socket
  state)

(defvar *active-connections* nil)
(defparameter *default-port* 8080)
(defconstant +max-headers+ 100)

(define-condition server-error (error)
  ((reason :initarg :reason :reader error-reason)))

(defclass server ()
  ((host :initarg :host :accessor server-host)
   (port :initarg :port :accessor server-port)
   (handler :initarg :handler :accessor server-handler)))

(defclass ssl-server (server)
  ((cert-path :initarg :cert-path :accessor ssl-cert-path)))

(defgeneric process-request (server request))

(defmethod process-request ((srv server) (req string))
  "Process an incoming HTTP request."
  (let ((parsed (parse-headers req)))
    (funcall (server-handler srv) parsed)))

;; Custom definer (Franz-style) — should be picked up by the def-prefix heuristic
(definline-maybe header= (a b)
  "Fast header equality."
  (string-equal a b))

(definline header< (a b)
  (string< a b))

(defun make-server (host port handler)
  "Create a new server instance."
  (make-instance 'server :host host :port port :handler handler))

(defun start (server)
  "Start the server listening on its configured port."
  (format t "Starting server on ~a:~a~%" (server-host server) (server-port server))
  (process-request server "GET / HTTP/1.1"))

(defun stop (server)
  (format t "Stopping server~%"))

(defun compare-headers (h1 h2)
  "Compare two headers using the custom definers."
  (or (header= h1 h2) (header< h1 h2)))

(defmacro with-server ((var host port handler) &body body)
  "Execute body with a running server bound to var."
  `(let ((,var (make-server ,host ,port ,handler)))
     (unwind-protect
       (progn (start ,var) ,@body)
       (stop ,var))))
