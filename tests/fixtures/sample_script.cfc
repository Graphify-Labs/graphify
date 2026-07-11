component extends="base.BaseComponent" implements="IWidget" {

	property name="id" type="numeric";

	function init(numeric id) {
		variables.id = id;
		return this;
	}

	function load() {
		var result = queryFetch();
		var helper = createObject("component", "utils.Helper");
		return helper.process(result);
	}

	private function queryFetch() {
		var q = new Query();
		return q.execute();
	}

}
