<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<%@ page import="com.example.shop.Product, java.util.List" %>
<%@ page import="java.util.*" %>
<%@ page import="com.example.shop.OrderService,
                 java.text.NumberFormat" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<%@ taglib prefix="shop" tagdir="/WEB-INF/tags" %>
<%-- <%@ page import="com.example.legacy.OldCart" %> --%>
<%-- <jsp:include page="/WEB-INF/views/common/old-banner.jsp"/> --%>
<%@ include file="/WEB-INF/views/common/header.jspf" %>
<jsp:useBean id="orders" class="com.example.shop.OrderService" scope="request"/>
<%!
    private String formatPrice(int cents) {
        if (cents < 0) {
            return "-";
        }
        return NumberFormat.getCurrencyInstance().format(cents / 100.0);
    }

    public int countItems(List<Product> items) {
        return items.size();
    }
%>
<h1>Orders</h1>
<ul>
<% for (Product p : orders.listItems()) { %>
  <li><%= p.getName() %>: <%= formatPrice(p.getPriceCents()) %></li>
<% } %>
</ul>
<jsp:include page="../common/footer.jsp">
  <jsp:param name="year" value="2026"/>
</jsp:include>
<jsp:include page="<%= request.getParameter(\"extra\") %>"/>
<jsp:include page="${extraFragment}"/>
<jsp:include page="sidebar.jsp"/>
