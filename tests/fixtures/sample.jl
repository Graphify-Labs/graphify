module Geometry

using LinearAlgebra
import Base: show
using Base.Threads
using ..ParentModule

abstract type Shape end

struct Point <: Shape
    x::Float64
    y::Float64
end

mutable struct Circle <: Shape
    center::Point
    radius::Float64
end

function area(c::Circle)
    return pi * c.radius^2
end

function distance(p1::Point, p2::Point)
    return norm([p1.x - p2.x, p1.y - p2.y])
end

perimeter(c::Circle) = 2 * pi * c.radius

function describe(s::Shape)
    show(s)
    area(s)
end

end
