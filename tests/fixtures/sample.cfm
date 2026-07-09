<cfinclude template="header.cfm">
<cfimport taglib="/myapp/components" prefix="app">
<cfset obj = createObject("component", "models.User")>
<cfoutput>#obj.getName()#</cfoutput>
