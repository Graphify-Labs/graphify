<cfcomponent displayname="Widget" extends="base.BaseComponent" implements="IWidget" output="false">

	<cfproperty name="id" type="numeric">

	<cffunction name="init" access="public" returntype="Widget">
		<cfargument name="id" type="numeric" required="true">
		<cfset variables.id = arguments.id>
		<cfreturn this>
	</cffunction>

	<cffunction name="load" access="public" returntype="void">
		<cfset var result = queryFetch()>
		<cfset local.helper = createObject("component", "utils.Helper")>
		<cfreturn helper.process(result)>
	</cffunction>

	<cfscript>
		private function queryFetch() {
			var q = new Query();
			q.setSQL("SELECT * FROM widgets");
			return q.execute();
		}
	</cfscript>

</cfcomponent>
