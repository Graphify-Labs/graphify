#import <Foundation/Foundation.h>
#import "SampleDelegate.h"

@interface Animal : NSObject <SampleDelegate>

@property (nonatomic, strong) NSString *name;

- (instancetype)initWithName:(NSString *)name;
- (void)speak;

@end

@implementation Animal

- (instancetype)initWithName:(NSString *)name {
    self = [super init];
    if (self) {
        _name = name;
    }
    return self;
}

- (void)speak {
    NSLog(@"%@ makes a sound.", self.name);
}

@end

@interface Dog : Animal

- (void)fetch;

@end

@implementation Dog

- (void)fetch {
    [self speak];
    NSLog(@"%@ fetches the ball!", self.name);
}

@end

@protocol Base

- (void)baseMethod;

@end

@protocol Derived <Base>

- (void)derivedMethod;

@end
