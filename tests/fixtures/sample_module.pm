package Acme::Widget;

use strict;
use warnings;
use Scalar::Util qw(blessed);
use Carp;
require Acme::Helper;

use parent -norequire, 'Acme::Role';
use base 'Acme::Mixin';

our @ISA = ('Acme::Base');

sub new {
    my ($class, %args) = @_;
    my $self = { %args };
    return bless $self, $class;
}

sub render {
    my $self = shift;
    my $line = format_line();
    Acme::Helper::emit($line);
    $self->update();
    return $line;
}

sub format_line {
    return "rendered";
}

sub update {
    my $self = shift;
    $self->{dirty} = 1;
    return $self;
}

package Acme::Widget::Inner;

use POSIX qw(floor);

sub tick {
    return floor(1.5);
}

1;
