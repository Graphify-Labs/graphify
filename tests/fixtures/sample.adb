with Ada.Text_IO;
with Ada.Integer_Text_IO;

package body Sample_Package is

   procedure Initialize(C : in out Counter_Type) is
   begin
      C.Value := 0;
   end Initialize;

   function Get_Value(C : Counter_Type) return Integer is
   begin
      return C.Value;
   end Get_Value;

   overriding procedure Speak (D : Dog_Type) is
   begin
      Ada.Text_IO.Put_Line ("Woof");
      Helper (D.ID);
   exception
      when Constraint_Error =>
         Handle_Constraint_Error;
      when My_Error =>
         Handle_My_Error;
   end Speak;

   procedure Safe_Operation is
   begin
      if Counter < 0 then
         raise Program_Error with "negative counter";
      end if;
   exception
      when others =>
         null;
   end Safe_Operation;

   task body Worker_Task is
      Local : Integer := Compute (42);
   begin
      accept Start do
         Ada.Text_IO.Put_Line("Worker started");
         Process (Local);
      end Start;

      accept Stop do
         Ada.Text_IO.Put_Line("Worker stopped");
      end Stop;
   end Worker_Task;

   protected body Shared_Counter is

      procedure Increment is
      begin
         Count := Count + 1;
         Notify;
      end Increment;

      function Get_Count return Integer is
      begin
         return Count;
      end Get_Count;

   end Shared_Counter;

   package body Generic_Img is
      Current : Item;

      function To_String (I : Item) return String is
      begin
         return Image (I);
      end To_String;
   end Generic_Img;

   package Integer_Container is new Generic_Img (Integer, Image => Integer_Text_IO.Image);

end Sample_Package;
