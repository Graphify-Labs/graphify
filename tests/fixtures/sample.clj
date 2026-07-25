(ns sample.core
  (:require [sample.db :as db]
            [clojure.string :as str]
            sample.audit)
  (:import [java.time Instant]))

(defonce default-role :guest)

(defprotocol Store
  (fetch-user [this id])
  (save-user! [this user]))

(defrecord User [id name]
  Store
  (fetch-user [this id]
    (normalize-name name))
  (save-user! [this user]
    user))

(deftype Cache [state]
  Store
  (fetch-user [this id]
    (normalize-name id))
  (save-user! [this user]
    user))

(defn normalize-name [name]
  (str/trim name))

(defn- enrich-user [user]
  (normalize-name (:name user)))

(defn quoted-example []
  '(normalize-name "quoted"))

(defn syntax-quoted-example []
  `(normalize-name "syntax-quoted"))

(defn var-quoted-example []
  #'normalize-name)

(defn comment-example []
  (comment
    (normalize-name "commented"))
  nil)

(defn discarded-example []
  #_(normalize-name "discarded")
  nil)

(defmacro with-user [binding & body]
  `(let [~binding (fetch-current)]
     ~@body))

(defmulti render :type)

(defmethod render :user [user]
  (enrich-user user))

(defmethod render :admin [user]
  (normalize-name (:name user)))

(defn handle-request [id]
  (let [user (db/fetch-user id)]
    (render (assoc user :name (normalize-name (:name user))))))
