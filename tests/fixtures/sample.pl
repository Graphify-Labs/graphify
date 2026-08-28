#!/usr/bin/perl
use strict;
use warnings;
use Acme::Widget;

package Acme::Helper;

sub emit {
    my ($text) = @_;
    print "$text\n";
    return length $text;
}

sub format {
    my ($text) = @_;
    return uc $text;
}

package main;

sub run_report {
    my $widget = Acme::Widget->new();
    $widget->render();
    Acme::Helper::emit("done");
}

run_report();
