defmodule MyApp.Accounts.User do
  @moduledoc """
  Handles user accounts and authentication.
  """

  alias MyApp.Repo
  alias MyApp.Schemas.{Account, Token}
  import Ecto.Query

  defstruct [:id, :name, :email]

  def create(attrs) do
    %__MODULE__{}
    |> validate(attrs)
    |> Repo.insert()
  end

  def find(id) do
    Repo.get(__MODULE__, id)
  end

  defp validate(user, attrs) do
    if Map.has_key?(attrs, :email) do
      user
    else
      {:error, :missing_email}
    end
  end
end
