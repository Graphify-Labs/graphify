with Ada.Text_IO;
with Ada.Integer_Text_IO;
with Ada.Containers.Vectors;

package Sample_Package is

   type Base_Type is tagged record
      ID : Integer;
   end record;

   type Derived_Type is new Base_Type with record
      Extra : Float;
   end record;

   type Animal_Interface is interface;
   procedure Speak (A : Animal_Interface) is abstract;

   type Dog_Type is new Base_Type and Animal_Interface with record
      Breed : String(1..20);
   end record;

   overriding procedure Speak (D : Dog_Type);

   subtype Positive_Integer is Integer range 1 .. Integer'Last;

   type Color_Enum is (Red, Green, Blue);

   type Color_Array is array (Color_Enum) of Integer;

   type Access_To_Integer is access all Integer;

   type Func_Access is access function (X : Integer) return Integer;

   type Record_With_Access is record
      Ptr : Access_To_Integer;
   end record;

   Max_Size : constant Integer := 100;
   Counter  : Integer := 0;

   My_Error : exception;

   function Expr_Func (X : Integer) return Integer is (X * 2);

   procedure Null_Proc;

   package Vec_Pkg is new Ada.Containers.Vectors (Integer, Integer);

   generic
      type Item is private;
      with function Image (I : Item) return String;
   package Generic_Img is
      function To_String (I : Item) return String;
   end Generic_Img;

   type Counter_Type is record
      Value : Integer;
      Name  : String(1..10);
   end record;

   procedure Initialize(C : in out Counter_Type);

   function Get_Value(C : Counter_Type) return Integer;

   task type Worker_Task is
      entry Start;
      entry Stop;
   end Worker_Task;

    protected type Shared_Counter is
       procedure Increment;
       function Get_Count return Integer;
    private
       Count : Integer := 0;
    end Shared_Counter;

    -- Single task declaration
    task Monitor_Task is
       entry Check;
    end Monitor_Task;

    -- Single protected object declaration
    protected Shared_Buffer is
       procedure Add(Item : Integer);
       function Get return Integer;
    private
       Data : Integer := 0;
    end Shared_Buffer;

    -- Object renaming declaration
    Renamed_Value : Integer renames Counter;

end Sample_Package;
