%macro greet(name);
  %put Hello &name;
%mend greet;

data work.customers;
  set raw.import;
  length name $ 50;
run;

proc sort data=work.customers;
  by name;
run;

%greet(World);
