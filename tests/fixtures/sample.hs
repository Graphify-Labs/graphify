module Sample where

import Data.List (sort)
import qualified Data.Map as Map
import Control.Monad (forM_)

data Shape = Circle Double | Square Double

class Describable a where
  describe :: a -> String

instance Describable Shape where
  describe (Circle r) = "circle"
  describe (Square s) = "square"

area :: Shape -> Double
area (Circle r) = 3.14 * r * r
area (Square s) = s * s

totalArea :: [Shape] -> Double
totalArea shapes = sum (map area shapes)

main :: IO ()
main = forM_ [Circle 1.0] (\s -> putStrLn (describe s))
